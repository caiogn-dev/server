"""
Unified automation service.

Pipeline (em ordem de prioridade):
1. IntentDetector  → regex rápido, sem custo
2. IntentHandler   → resposta determinística por intenção
3. AutoMessage DB  → templates configurados pelo operador
4. LangchainService → agente LLM configurado na conta
5. Fallback        → texto genérico de direcionamento

Métricas estruturadas emitidas em cada etapa:
  unified.intent        — intenção detectada
  unified.source        — onde a resposta foi gerada (handler/template/llm/fallback)
  unified.duration_ms   — tempo total de processamento
  unified.llm_used      — se o LLM foi invocado
  unified.store_id      — loja resolvida (None se não encontrada)
"""
import logging
import re
import time
import unicodedata
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from apps.agents.models import AgentConversation
from apps.agents.services import LangchainService
from apps.automation.models import AutoMessage, CustomerSession
from apps.automation.services.context_service import AutomationContextService
from apps.whatsapp.intents.detector import IntentDetector, IntentType
from apps.whatsapp.intents.handlers import get_handler

logger = logging.getLogger(__name__)

# ─── Validação de botões WhatsApp ────────────────────────────────────────────
_BUTTON_TITLE_MAX = 20
_BUTTON_ID_MAX = 256


def _validate_buttons(buttons: Optional[List[Dict]]) -> Optional[List[Dict]]:
    """
    Valida e normaliza a lista de botões para o formato esperado pela API WhatsApp.

    - Remove botões sem 'id' ou sem 'title'
    - Trunca title em 20 chars e id em 256 chars (limites da API)
    - Retorna None se a lista ficar vazia após filtragem
    """
    if not buttons:
        return None
    valid = []
    for btn in buttons:
        btn_id = str(btn.get('id', '')).strip()
        btn_title = str(btn.get('title', '')).strip()
        if not btn_id or not btn_title:
            logger.warning('[UnifiedService] Botão inválido ignorado: %s', btn)
            continue
        valid.append({
            'id': btn_id[:_BUTTON_ID_MAX],
            'title': btn_title[:_BUTTON_TITLE_MAX],
        })
    return valid or None


class ResponseSource(Enum):
    TEMPLATE = 'template'
    LLM = 'llm'
    HANDLER = 'handler'
    FALLBACK = 'fallback'


@dataclass
class UnifiedResponse:
    content: str
    source: ResponseSource
    buttons: Optional[List[Dict[str, str]]] = None
    header: Optional[str] = None
    footer: Optional[str] = None
    metadata: Optional[dict] = None
    interactive_type: Optional[str] = None
    interactive_data: Optional[dict] = None


class UnifiedService:
    """Single entry point for automated WhatsApp replies."""

    CONSULTATIVE_INTENTS = {
        IntentType.GREETING,
        IntentType.PRICE_CHECK,
        IntentType.DELIVERY_INFO,
        IntentType.MENU_REQUEST,
        IntentType.LOCATION,
        IntentType.CONTACT,
        IntentType.FAQ,
        IntentType.PRODUCT_INQUIRY,
        IntentType.CUSTOMIZATION,
        IntentType.COMPARISON,
        IntentType.RECOMMENDATION,
        IntentType.COMPLAINT,
        IntentType.GENERAL_QUESTION,
        IntentType.UNKNOWN,
    }

    OUT_OF_HOURS_INTENTS = {
        IntentType.GREETING,
        IntentType.MENU_REQUEST,
        IntentType.PRODUCT_INQUIRY,
        IntentType.PRODUCT_MENTION,
        IntentType.CREATE_ORDER,
        IntentType.ADD_TO_CART,
        IntentType.DELIVERY_INFO,
        IntentType.PRICE_CHECK,
        IntentType.RECOMMENDATION,
    }

    def __init__(self, account, conversation, debug: bool = False, use_llm: bool = True):
        self.account = account
        self.conversation = conversation
        self.debug = debug
        self.context = AutomationContextService.resolve(
            account=account,
            conversation=conversation,
            create_profile=False,
        )
        self.company = self.context.profile
        self.store = self.context.store
        self.agent = AutomationContextService.get_default_agent(context=self.context)
        self.use_llm = bool(use_llm) and AutomationContextService.is_ai_enabled(
            context=self.context,
            conversation=conversation,
        )
        self.detector = IntentDetector(use_llm_fallback=self.use_llm)
        self.stats = {'template': 0, 'llm': 0, 'handler': 0, 'fallback': 0}

    def _map_intent_to_event(self, intent: IntentType) -> str:
        mapping = {
            IntentType.GREETING: 'welcome',
            IntentType.MENU_REQUEST: 'menu',
            IntentType.PRODUCT_INQUIRY: 'menu',
            IntentType.PRODUCT_MENTION: 'menu',
            IntentType.ADD_TO_CART: 'cart_created',
            IntentType.CREATE_ORDER: 'order_received',
            IntentType.TRACK_ORDER: 'order_confirmed',
            IntentType.PAYMENT_STATUS: 'payment_confirmed',
            IntentType.REQUEST_PIX: 'pix_generated',
            IntentType.CONFIRM_PAYMENT: 'payment_confirmed',
            IntentType.BUSINESS_HOURS: 'business_hours',
            IntentType.LOCATION: 'business_hours',
            IntentType.FAQ: 'faq',
        }
        return mapping.get(intent, 'custom')

    def _get_template_for_intent(self, intent: IntentType) -> Optional[AutoMessage]:
        if not self.company:
            return None

        return AutoMessage.objects.filter(
            company=self.company,
            event_type=self._map_intent_to_event(intent),
            is_active=True,
        ).order_by('priority').first()

    def _get_session_data(self) -> Dict[str, Any]:
        phone_number = self.conversation.phone_number
        sessions = CustomerSession.objects.filter(phone_number=phone_number)

        if self.company:
            sessions = sessions.filter(company=self.company)

        session = sessions.filter(
            status__in=['active', 'cart_created', 'checkout', 'payment_pending']
        ).order_by('-updated_at').first()

        if not session:
            return {'has_cart': False, 'cart_total': 0, 'cart_items_count': 0, 'has_order': False}

        return {
            'has_cart': bool(session.cart_data),
            'cart_total': float(session.cart_total or 0),
            'cart_items_count': session.cart_items_count,
            'has_order': bool(session.order_id),
            'order_id': session.order_id,
            'pix_pending': bool(session.pix_code and not session.payment_id),
        }

    def _normalize_lookup_text(self, value: str) -> str:
        if not value:
            return ''
        normalized = unicodedata.normalize('NFD', value.lower())
        normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
        return re.sub(r'[^a-z0-9\s]', ' ', normalized).strip()

    def _message_matches_catalog_product(self, message: str) -> bool:
        """Return True when free text is very likely a product name from this store."""
        if not self.store or not message:
            return False

        normalized_message = self._normalize_lookup_text(message)
        if len(normalized_message) < 3:
            return False

        try:
            from apps.stores.models import StoreProduct

            products = StoreProduct.objects.filter(
                store=self.store,
                is_active=True,
            ).exclude(tags__contains=['ingrediente']).only('name')

            for product in products:
                normalized_name = self._normalize_lookup_text(product.name)
                if not normalized_name:
                    continue
                if normalized_message == normalized_name:
                    return True
                if len(normalized_message) >= 5 and (
                    normalized_message in normalized_name or normalized_name in normalized_message
                ):
                    return True
        except Exception as exc:
            logger.warning('[unified] Product lookup failed before LLM routing: %s', exc)

        return False

    def _build_context(self, intent_data: Dict[str, Any], session_data: Dict[str, Any]) -> str:
        parts: List[str] = []

        if self.store:
            parts.append(f'Loja: {self.store.name}')
            parts.append(f'Tipo: {self.store.store_type}')
            if self.store.description:
                parts.append(f'Descricao: {self.store.description}')

        intent = intent_data.get('intent')
        if intent:
            parts.append(f'Intencao detectada: {intent.value}')

        if session_data.get('has_cart'):
            parts.append(f"Carrinho atual: R$ {session_data.get('cart_total', 0):.2f}")
            parts.append(f"Itens no carrinho: {session_data.get('cart_items_count', 0)}")

        if session_data.get('has_order'):
            parts.append(f"Pedido relacionado: {session_data.get('order_id')}")

        if self.store:
            from apps.stores.models import StoreProduct

            products = StoreProduct.objects.filter(store=self.store, is_active=True)[:5]
            if products:
                product_lines = [f'- {product.name}: R$ {product.price:.2f}' for product in products]
                parts.append('Produtos ativos:')
                parts.extend(product_lines)

        return '\n'.join(parts)

    def _build_out_of_hours_fallback(self) -> str:
        """Return a concise out-of-hours message using store hours when available."""
        if not self.store:
            return (
                "Agora estamos fora do horário de atendimento.\n"
                "Me mande sua mensagem e eu continuo assim que a loja abrir."
            )

        store_name = self.store.name
        hours = getattr(self.store, 'operating_hours', None) or {}
        now = timezone.localtime()
        today = now.strftime('%A').lower()
        today_hours = hours.get(today) or {}

        lines = [f"{store_name} está fora do horário no momento."]
        if today_hours.get('open') and today_hours.get('close'):
            lines.append(f"Hoje atendemos de {today_hours['open']} às {today_hours['close']}.")
        lines.append("Você pode me enviar sua mensagem agora que seguimos assim que a loja abrir.")
        return "\n".join(lines)

    def _get_out_of_hours_response(self, session_data: Dict[str, Any]) -> Optional[UnifiedResponse]:
        """Resolve a configured out-of-hours template or a safe fallback text."""
        if not self.company:
            return UnifiedResponse(
                content=self._build_out_of_hours_fallback(),
                source=ResponseSource.TEMPLATE,
                metadata={'event_type': 'out_of_hours', 'intent': 'out_of_hours'},
            )

        template = AutoMessage.objects.filter(
            company=self.company,
            event_type=AutoMessage.EventType.OUT_OF_HOURS,
            is_active=True,
        ).order_by('priority').first()

        if template:
            validated_buttons = _validate_buttons(template.buttons)
            return UnifiedResponse(
                content=self._render_template(template, session_data),
                source=ResponseSource.TEMPLATE,
                buttons=validated_buttons,
                metadata={
                    'template_id': str(template.id),
                    'event_type': template.event_type,
                    'intent': 'out_of_hours',
                },
                interactive_type='buttons' if validated_buttons else None,
                interactive_data={'buttons': validated_buttons} if validated_buttons else None,
            )

        return UnifiedResponse(
            content=self._build_out_of_hours_fallback(),
            source=ResponseSource.TEMPLATE,
            metadata={'event_type': 'out_of_hours', 'intent': 'out_of_hours'},
        )

    def _render_template(self, template: AutoMessage, session_data: Dict[str, Any]) -> str:
        """
        Renderiza um template substituindo variáveis por valores reais.

        Variáveis suportadas:
          {customer_name}  — nome do contato (fallback: 'Cliente')
          {company_name}   — nome da empresa (fallback: 'Nossa Loja')
          {phone}          — telefone do contato
          {cart_total}     — valor total do carrinho (R$ XX.XX)
          {cart_items}     — quantidade de itens no carrinho
          {order_id}       — ID do pedido, SOMENTE se disponível na sessão

        Variáveis cujo dado está ausente são substituídas pela string vazia
        para evitar mensagens com placeholders visíveis ao cliente.
        """
        def _safe(value, default: str = '') -> str:
            return str(value) if value is not None else default

        order_id = session_data.get('order_id')
        cart_total = float(session_data.get('cart_total') or 0)

        replacements = {
            '{customer_name}': _safe(self.conversation.contact_name, 'Cliente'),
            '{company_name}': _safe(self.company.company_name if self.company else None, 'Nossa Loja'),
            '{phone}': _safe(self.conversation.phone_number),
            '{cart_total}': f'R$ {cart_total:.2f}',
            '{cart_items}': _safe(session_data.get('cart_items_count'), '0'),
            # {order_id} só aparece se há um pedido real — evita "Pedido: None"
            '{order_id}': _safe(order_id) if order_id else '',
        }

        content = template.message_text
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)

        # Detectar placeholders não substituídos e alertar em log
        remaining = re.findall(r'\{[a-z_]+\}', content)
        if remaining:
            logger.warning(
                '[UnifiedService] Template %s contém placeholders não resolvidos: %s',
                template.id, remaining,
            )

        return content

    def _should_use_llm(self, intent: IntentType) -> bool:
        """
        LLM should only handle consultative intents.
        Transactional flows such as order creation, PIX, payment confirmation,
        and order tracking must stay centralized in handlers/templates.
        """
        return self.use_llm and intent in self.CONSULTATIVE_INTENTS

    def _has_pending_delivery_address_session(self) -> bool:
        """Return True when this customer has an order waiting for delivery address."""
        if not self.conversation:
            return False

        phone_number = self.conversation.phone_number
        digits_only = re.sub(r'\D', '', phone_number or '')
        phone_candidates = [phone_number]
        if digits_only:
            phone_candidates.extend([digits_only, f'+{digits_only}'])
        phone_candidates = [value for value in dict.fromkeys(phone_candidates) if value]

        sessions = CustomerSession.objects.filter(
            phone_number__in=phone_candidates,
            status__in=['active', 'cart_created', 'checkout', 'payment_pending'],
            cart_data__waiting_for_address=True,
        )
        if self.company:
            sessions = sessions.filter(company=self.company)
        elif self.store:
            sessions = sessions.filter(company__store=self.store)

        return sessions.exists()

    def _has_pending_notes_session(self) -> bool:
        """Return True when this customer is in the notes collection step of checkout."""
        if not self.conversation:
            return False

        phone_number = self.conversation.phone_number
        digits_only = re.sub(r'\D', '', phone_number or '')
        phone_candidates = [phone_number]
        if digits_only:
            phone_candidates.extend([digits_only, f'+{digits_only}'])
        phone_candidates = [value for value in dict.fromkeys(phone_candidates) if value]

        sessions = CustomerSession.objects.filter(
            phone_number__in=phone_candidates,
            status__in=['active', 'cart_created', 'checkout', 'payment_pending'],
            cart_data__waiting_for_notes=True,
        )
        if self.company:
            sessions = sessions.filter(company=self.company)
        elif self.store:
            sessions = sessions.filter(company__store=self.store)

        return sessions.exists()

    def _is_human_mode_transactional_step(
        self,
        message_text: str,
        interactive_reply: Optional[Dict[str, Any]] = None,
        location_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Human mode blocks normal automation, but order checkout steps are safe to
        continue because they are deterministic and write the StoreOrder.
        """
        reply_id = str((interactive_reply or {}).get('id') or '')
        if (
            reply_id in {'order_delivery', 'order_pickup', 'pay_pix', 'pay_card', 'pay_pickup'}
            or reply_id.startswith('add_')
            or reply_id.startswith('product_')
        ):
            return True

        if location_data and location_data.get('lat') and location_data.get('lng'):
            return self._has_pending_delivery_address_session()

        if (message_text or '').strip():
            return (
                self._has_pending_delivery_address_session()
                or self._has_pending_notes_session()
            )

        return False

    def _run_handler(self, intent_data: Dict[str, Any]) -> Optional[UnifiedResponse]:
        intent = intent_data.get('intent', IntentType.UNKNOWN)
        handler = get_handler(intent, self.account, self.conversation)
        if not handler:
            return None

        if self.company:
            handler.company_profile = self.company
        if self.store:
            handler.store = self.store

        try:
            result = handler.handle(intent_data)
        except Exception as exc:
            logger.error(
                '[unified] Handler %s raised exception for intent=%s: %s',
                handler.__class__.__name__, intent.value, exc,
                exc_info=True,
            )
            return None

        if not result:
            return None

        if result.requires_llm:
            return None

        if result.use_interactive:
            interactive_data = result.interactive_data or {}
            self.stats['handler'] += 1
            return UnifiedResponse(
                content=interactive_data.get('body') or result.response_text or '',
                source=ResponseSource.HANDLER,
                buttons=interactive_data.get('buttons'),
                header=interactive_data.get('header'),
                footer=interactive_data.get('footer'),
                metadata={'intent': intent.value, 'handler': handler.__class__.__name__},
                interactive_type=result.interactive_type,
                interactive_data=interactive_data,
            )

        if result.response_text and result.response_text not in {'BUTTONS_SENT', 'LIST_SENT', 'INTERACTIVE_SENT'}:
            self.stats['handler'] += 1
            return UnifiedResponse(
                content=result.response_text,
                source=ResponseSource.HANDLER,
                metadata={'intent': intent.value, 'handler': handler.__class__.__name__},
            )

        return None

    def _call_llm(self, message: str, context_text: str) -> Optional[str]:
        """
        Invoca o agente LLM configurado para a conta.

        Retorna a resposta em texto ou None se:
        - LLM não está habilitado para esta conta
        - Nenhum agente está configurado
        - O agente retornou resposta vazia
        - Ocorreu erro na chamada (logado como ERROR)

        IMPORTANTE: persiste AgentConversation no DB após cada chamada bem-sucedida
        para garantir que o session_id do Redis seja reutilizado nas próximas mensagens.
        Sem isso, cada mensagem geraria um novo session_id e a memória seria perdida.
        """
        if not self.use_llm or not self.agent:
            return None

        _t0 = time.monotonic()
        try:
            service = LangchainService(self.agent)

            # Busca conversa existente para reutilizar o session_id do Redis
            agent_conversation = AgentConversation.objects.filter(
                agent=self.agent,
                phone_number=self.conversation.phone_number,
            ).order_by('-last_message_at').first()
            # Use a stable Redis memory key even before the DB tracking row exists.
            # This avoids context loss when two inbound messages for the same
            # WhatsApp conversation are processed concurrently.
            session_id = (
                str(agent_conversation.session_id)
                if agent_conversation
                else str(self.conversation.id)
            )

            # Passa a mensagem diretamente — LangchainService já constrói o contexto
            # completo (cardápio, pedidos, horários) via _build_dynamic_context().
            # Não enriquecer aqui evita duplicação de contexto no prompt.
            result = service.process_message(
                message=message,
                session_id=session_id,
                phone_number=self.conversation.phone_number,
                conversation_id=str(self.conversation.id),
            )
            response_text = result.get('response', '').strip()
            used_session_id = result.get('session_id', session_id)

            # Persiste/atualiza AgentConversation no DB para que o próximo turno
            # encontre o mesmo session_id e reutilize a memória Redis.
            if used_session_id:
                from django.db import IntegrityError, transaction

                defaults = {
                    'session_id': used_session_id,
                    'whatsapp_conversation': self.conversation,
                    'metadata': {'last_response_ms': round((time.monotonic() - _t0) * 1000, 1)},
                }
                try:
                    with transaction.atomic():
                        existing = (
                            AgentConversation.objects
                            .select_for_update()
                            .filter(agent=self.agent, phone_number=self.conversation.phone_number)
                            .order_by('-last_message_at')
                            .first()
                        )
                        if existing:
                            for field, value in defaults.items():
                                setattr(existing, field, value)
                            existing.save(update_fields=['session_id', 'whatsapp_conversation', 'metadata', 'updated_at'])
                        else:
                            AgentConversation.objects.create(
                                agent=self.agent,
                                phone_number=self.conversation.phone_number,
                                **defaults,
                            )
                except IntegrityError:
                    AgentConversation.objects.filter(
                        agent=self.agent,
                        phone_number=self.conversation.phone_number,
                    ).update(
                        whatsapp_conversation=self.conversation,
                        metadata=defaults['metadata'],
                    )

            _llm_ms = round((time.monotonic() - _t0) * 1000, 1)
            logger.info(
                '[unified] LLM response ok (%.0fms) agent=%s session=%s tokens=%s',
                _llm_ms, self.agent.id, used_session_id,
                result.get('tokens_used', '?'),
                extra={'unified.llm_used': True, 'unified.llm_duration_ms': _llm_ms},
            )
            return response_text or None
        except Exception as exc:
            _llm_ms = round((time.monotonic() - _t0) * 1000, 1)
            logger.error(
                '[unified] LLM error after %.0fms: %s — agent=%s provider=%s model=%s',
                _llm_ms, exc,
                getattr(self.agent, 'id', '?'),
                getattr(self.agent, 'provider', '?'),
                getattr(self.agent, 'model_name', '?'),
                exc_info=True,
                extra={'unified.llm_used': True, 'unified.llm_error': str(exc)},
            )
            return None

    def process_message(
        self,
        message_text: str,
        interactive_reply: Optional[Dict[str, Any]] = None,
        location_data: Optional[Dict[str, Any]] = None,
    ) -> Optional['UnifiedResponse']:
        """
        Processa uma mensagem e retorna a melhor resposta disponível.

        Args:
            message_text:       Texto da mensagem do cliente.
            interactive_reply:  Se presente, indica que o cliente clicou em um
                                botão/item de lista. Dict com 'type', 'id' e 'title'.
                                Nesse caso, o pipeline pula a detecção de intenção e
                                roteia diretamente para InteractiveReplyHandler.

        Emite log estruturado ao final com:
          unified.intent, unified.source, unified.duration_ms, unified.store_id
        """
        if (
            self.conversation
            and getattr(self.conversation, 'mode', None) == 'human'
            and not self._is_human_mode_transactional_step(
                message_text,
                interactive_reply=interactive_reply,
                location_data=location_data,
            )
        ):
            logger.info(
                '[unified] Conversation in human mode — skipping automation',
                extra={'conversation_id': str(self.conversation.pk)},
            )
            return None

        _t0 = time.monotonic()
        _store_id = str(self.store.id) if self.store else None

        # ── Caminho rápido: resposta interativa (clique em botão / lista) ──
        if interactive_reply:
            from apps.whatsapp.intents.handlers import InteractiveReplyHandler
            try:
                handler = InteractiveReplyHandler(self.account, self.conversation, self.company)
                if self.store:
                    handler.store = self.store
                result = handler.handle({
                    'reply_id': interactive_reply.get('id', ''),
                    'reply_title': interactive_reply.get('title', ''),
                    'original_message': message_text or '',
                })
                if result and not result.requires_llm:
                    _ms = round((time.monotonic() - _t0) * 1000, 1)
                    logger.info(
                        '[unified] interactive_reply handler (%.0fms) reply_id=%s',
                        _ms, interactive_reply.get('id'),
                        extra={
                            'unified.source': 'handler',
                            'unified.intent': 'interactive_reply',
                            'unified.duration_ms': _ms,
                            'unified.store_id': _store_id,
                        },
                    )
                    self.stats['handler'] += 1
                    if result.use_interactive:
                        interactive_data = result.interactive_data or {}
                        return UnifiedResponse(
                            content=interactive_data.get('body') or result.response_text or '',
                            source=ResponseSource.HANDLER,
                            buttons=interactive_data.get('buttons'),
                            header=interactive_data.get('header'),
                            footer=interactive_data.get('footer'),
                            metadata={'intent': 'interactive_reply'},
                            interactive_type=result.interactive_type,
                            interactive_data=interactive_data,
                        )
                    if result.response_text not in {None, '', 'BUTTONS_SENT', 'LIST_SENT', 'INTERACTIVE_SENT'}:
                        return UnifiedResponse(
                            content=result.response_text,
                            source=ResponseSource.HANDLER,
                            metadata={'intent': 'interactive_reply'},
                        )
            except Exception as exc:
                logger.error(
                    '[unified] InteractiveReplyHandler failed: %s', exc,
                    extra={'unified.source': 'error', 'message_id': message_text[:50]},
                )
            # Fall through to normal pipeline if handler didn't produce a response

        # ── Caminho rápido: mensagem de localização WhatsApp ──
        if location_data and location_data.get('lat') and location_data.get('lng'):
            from apps.whatsapp.intents.handlers import UnknownHandler
            try:
                handler = UnknownHandler(self.account, self.conversation, self.company)
                if self.store:
                    handler.store = self.store
                result = handler.handle({
                    'location': location_data,
                    'original_message': message_text or '',
                })
                if result and not result.requires_llm:
                    _ms = round((time.monotonic() - _t0) * 1000, 1)
                    logger.info(
                        '[unified] location handler (%.0fms)', _ms,
                        extra={'unified.source': 'handler', 'unified.intent': 'location',
                               'unified.duration_ms': _ms, 'unified.store_id': _store_id},
                    )
                    self.stats['handler'] += 1
                    if result.use_interactive:
                        interactive_data = result.interactive_data or {}
                        return UnifiedResponse(
                            content=interactive_data.get('body') or result.response_text or '',
                            source=ResponseSource.HANDLER,
                            buttons=interactive_data.get('buttons'),
                            header=interactive_data.get('header'),
                            footer=interactive_data.get('footer'),
                            metadata={'intent': 'location'},
                            interactive_type=result.interactive_type,
                            interactive_data=interactive_data,
                        )
                    if result.response_text not in {None, '', 'BUTTONS_SENT', 'LIST_SENT', 'INTERACTIVE_SENT'}:
                        return UnifiedResponse(
                            content=result.response_text,
                            source=ResponseSource.HANDLER,
                            metadata={'intent': 'location'},
                        )
            except Exception as exc:
                logger.error('[unified] location handler failed: %s', exc, exc_info=True)

        if not message_text or not message_text.strip():
            return UnifiedResponse(
                content='Desculpe, nao entendi. Pode repetir?',
                source=ResponseSource.FALLBACK,
                metadata={'unified.source': 'fallback_empty'},
            )

        normalized = message_text.strip()
        intent_data = self.detector.detect(normalized.lower())
        intent = intent_data.get('intent', IntentType.UNKNOWN)

        if intent == IntentType.UNKNOWN and self._message_matches_catalog_product(normalized):
            intent = IntentType.PRODUCT_MENTION
            intent_data['intent'] = intent
            intent_data['method'] = 'catalog_match'
            intent_data['confidence'] = 0.98

        intent_data['llm_available'] = bool(self.use_llm and self.agent)

        if self.debug:
            logger.debug(
                '[unified] intent=%s llm=%s store=%s company=%s',
                intent.value, self.use_llm,
                getattr(self.store, 'slug', None),
                getattr(self.company, 'id', None),
            )

        session_data = self._get_session_data()

        if (
            self.store
            and not self.store.is_open()
            and intent in self.OUT_OF_HOURS_INTENTS
        ):
            response = self._get_out_of_hours_response(session_data)
            _ms = round((time.monotonic() - _t0) * 1000, 1)
            logger.info(
                '[unified] out_of_hours response (%.0fms) intent=%s',
                _ms, intent.value,
                extra={'unified.source': 'template', 'unified.intent': 'out_of_hours',
                       'unified.duration_ms': _ms, 'unified.store_id': _store_id},
            )
            self.stats['template'] += 1
            return response

        # 1. Handler determinístico
        handler_response = self._run_handler(intent_data)
        if handler_response is not None:
            _ms = round((time.monotonic() - _t0) * 1000, 1)
            logger.info(
                '[unified] handler response (%.0fms) intent=%s', _ms, intent.value,
                extra={'unified.source': 'handler', 'unified.intent': intent.value,
                       'unified.duration_ms': _ms, 'unified.store_id': _store_id},
            )
            self.stats['handler'] += 1
            return handler_response

        # 2. Template do banco de dados (determinístico, antes do LLM)
        # Pular template para intents consultivas quando há agente LLM ativo —
        # o agente responde de forma mais rica e contextualizada.
        _agent_intents = {
            IntentType.PRODUCT_INQUIRY, IntentType.MENU_REQUEST,
            IntentType.PRODUCT_MENTION, IntentType.FAQ,
            IntentType.BUSINESS_HOURS, IntentType.LOCATION,
        }
        _skip_template = (
            intent in _agent_intents
            and self.company
            and getattr(self.company, 'use_ai_agent', False)
            and getattr(self.company, 'default_agent', None)
        )
        template = None if _skip_template else self._get_template_for_intent(intent)
        if template:
            validated_buttons = _validate_buttons(template.buttons)
            _ms = round((time.monotonic() - _t0) * 1000, 1)
            logger.info(
                '[unified] template response (%.0fms) intent=%s template=%s',
                _ms, intent.value, template.id,
                extra={'unified.source': 'template', 'unified.intent': intent.value,
                       'unified.duration_ms': _ms, 'unified.store_id': _store_id},
            )
            self.stats['template'] += 1
            return UnifiedResponse(
                content=self._render_template(template, session_data),
                source=ResponseSource.TEMPLATE,
                buttons=validated_buttons,
                metadata={
                    'template_id': str(template.id),
                    'event_type': template.event_type,
                    'intent': intent.value,
                    'unified.duration_ms': _ms,
                },
                interactive_type='buttons' if validated_buttons else None,
                interactive_data={'buttons': validated_buttons} if validated_buttons else None,
            )

        # 3. LLM (somente para intents consultivas)
        if self._should_use_llm(intent):
            context_text = self._build_context(intent_data, session_data)
            llm_response = self._call_llm(normalized, context_text)
            if llm_response:
                _ms = round((time.monotonic() - _t0) * 1000, 1)
                logger.info(
                    '[unified] llm response (%.0fms) intent=%s agent=%s',
                    _ms, intent.value, getattr(self.agent, 'id', None),
                    extra={'unified.source': 'llm', 'unified.intent': intent.value,
                           'unified.duration_ms': _ms, 'unified.store_id': _store_id},
                )
                self.stats['llm'] += 1
                return UnifiedResponse(
                    content=llm_response,
                    source=ResponseSource.LLM,
                    metadata={
                        'intent': intent.value,
                        'agent_id': str(self.agent.id) if self.agent else None,
                        'unified.duration_ms': _ms,
                    },
                )

        # 4. Fallback genérico
        _ms = round((time.monotonic() - _t0) * 1000, 1)
        logger.warning(
            '[unified] fallback response (%.0fms) intent=%s — nenhum provider respondeu',
            _ms, intent.value,
            extra={'unified.source': 'fallback', 'unified.intent': intent.value,
                   'unified.duration_ms': _ms, 'unified.store_id': _store_id},
        )
        self.stats['fallback'] += 1
        return UnifiedResponse(
            content='Posso continuar pelo menu, te mostrar o catalogo ou encaminhar voce para um atendente humano.',
            source=ResponseSource.FALLBACK,
            metadata={
                'intent': intent.value,
                'unified.duration_ms': _ms,
            },
        )


LLMOrchestratorService = UnifiedService
