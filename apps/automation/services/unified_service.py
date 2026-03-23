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
            IntentType.UNKNOWN: 'welcome',
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
            session_id = str(agent_conversation.session_id) if agent_conversation else None

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
                from django.db.models import F
                AgentConversation.objects.update_or_create(
                    agent=self.agent,
                    phone_number=self.conversation.phone_number,
                    defaults={
                        'session_id': used_session_id,
                        'whatsapp_conversation': self.conversation,
                        'metadata': {'last_response_ms': round((time.monotonic() - _t0) * 1000, 1)},
                    },
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
    ) -> UnifiedResponse:
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

        if self.debug:
            logger.debug(
                '[unified] intent=%s llm=%s store=%s company=%s',
                intent.value, self.use_llm,
                getattr(self.store, 'slug', None),
                getattr(self.company, 'id', None),
            )

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

        # 2. LLM (agente conversacional com contexto completo, memória e ferramentas)
        session_data = self._get_session_data()
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

        # 3. Template do banco de dados (fallback quando LLM indisponível)
        template = self._get_template_for_intent(intent)
        if template:
            if not session_data:
                session_data = self._get_session_data()
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