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
from apps.agents.services import LangGraphService
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
    # Modo restrito (allowed_intents): intent fora da allow-list é silenciada
    # de propósito — o dispatcher trata como resposta OK (sem fallback/alerta).
    SUPPRESSED = 'suppressed'


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
        IntentType.PRODUCT_INQUIRY,
        IntentType.PRODUCT_MENTION,
        IntentType.CREATE_ORDER,
        IntentType.ADD_TO_CART,
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

    def _allowed_intents(self):
        """Allow-list de intents do modo restrito (None = modo desligado).

        profile.settings['allowed_intents'] = ['menu_request', ...] faz o
        pipeline responder SOMENTE essas intents e silenciar todo o resto
        (IA, fluxos interativos de pedido, mensagens automáticas).
        """
        settings_data = getattr(self.company, 'settings', None) or {}
        allowed = settings_data.get('allowed_intents')
        if isinstance(allowed, (list, tuple)) and allowed:
            return {str(item) for item in allowed}
        return None

    # Intents que fecham pedido pelo bot — gateadas pelo toggle bot_order_enabled
    ORDER_FLOW_INTENT_VALUES = {
        'create_order', 'add_to_cart', 'modify_order', 'confirm_payment',
        'request_pix', 'view_qr_code', 'copy_pix', 'product_mention',
    }
    # Cliques interativos que NÃO são fluxo de pedido (sempre permitidos)
    NON_ORDER_REPLY_IDS = {
        'view_menu', 'view_catalog', 'order_catalog', 'contact_support',
        'show_options', 'montar_salada',
    }

    def _bot_order_enabled(self) -> bool:
        # Gate de PLANO: bot de pedidos é feature Pro/Premium (isenta e trial
        # ativo passam). Erro interno de billing nunca derruba o bot.
        try:
            from apps.stores import billing
            store = getattr(self.company, 'store', None)
            if store is not None and not billing.bot_order_allowed(store):
                return False
        except Exception:
            logger.warning('[UnifiedService] Erro no gate de plano do bot', exc_info=True)
        settings_data = getattr(self.company, 'settings', None) or {}
        return bool(settings_data.get('bot_order_enabled', True))

    def _order_disabled_response(self) -> 'UnifiedResponse':
        menu_url = ''
        try:
            menu_url = self.company.get_menu_url() if self.company else ''
        except Exception:
            pass
        link = f"\n\n👉 {menu_url}" if menu_url else ''
        return UnifiedResponse(
            content=(
                "🛒 *Os pedidos são feitos pelo nosso site!*"
                f"{link}\n\n"
                "Por lá você monta o pedido completo, acompanha o status e paga "
                "com PIX ou cartão. Se preferir, é só chamar que um atendente te ajuda! 😊"
            ),
            source=ResponseSource.HANDLER,
            metadata={'intent': 'bot_order_disabled'},
        )

    def _suppressed(self, reason: str) -> 'UnifiedResponse':
        logger.info(
            '[unified] restricted mode: suprimido (%s)', reason,
            extra={'unified.source': 'suppressed', 'unified.intent': reason},
        )
        return UnifiedResponse(
            content='',
            source=ResponseSource.SUPPRESSED,
            metadata={'suppressed': True, 'reason': reason},
        )

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

    def _tem_agente_conversando(self) -> bool:
        """Loja com atendente de IA ativo — o LLM é quem conduz o diálogo."""
        return bool(
            self.use_llm
            and self.agent
            and getattr(self.company, 'use_ai_agent', False)
            and getattr(self.company, 'default_agent', None)
        )

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
                # Casamento PARCIAL só quando não há agente conversando.
                #
                # Com agente ativo, a mensagem curta quase sempre é RESPOSTA a
                # uma pergunta dele. Em 09/ago o cliente respondeu "Branco" à
                # pergunta "qual molho de cortesia você quer?" e a regra
                # `"branco" ⊂ "molho branco cremoso"` promoveu para
                # PRODUCT_MENTION: o handler despejou o card de venda de um
                # molho que era grátis, no meio do fluxo do combo.
                if self._tem_agente_conversando():
                    continue
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

            products = StoreProduct.disponiveis(self.store).exclude(tags__contains=['ingrediente'])[:5]
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
        _WEEKDAY = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        today = _WEEKDAY[now.weekday()]
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
        if not (self.use_llm and intent in self.CONSULTATIVE_INTENTS):
            return False
        # Não chamar LLM quando há pagamento PIX pendente — o agente re-envia o código
        # conversacionalmente, causando duplicidade de mensagens PIX na conversa.
        try:
            active = self._get_active_session()
            if active and active.status == 'payment_pending' and active.pix_code:
                return False
        except Exception:
            pass
        return True

    def _estado_deve_capturar(self, texto: str) -> bool:
        """O checkout em curso deve engolir esta mensagem?

        A pergunta era só "existe estado?" — e por isso "Quero salada" virou
        "✅ Anotado: Quero salada" no meio do checkout da Yeda, fechando um
        pedido de R$ 20 quando o real era R$ 100.

        Agora são duas: existe estado, E a mensagem pertence a ele. Pedir
        produto não pertence — segue para o roteamento normal. Endereço
        digitado, observação e qualquer outro texto continuam sendo capturados,
        que é o caso comum e não pode regredir.
        """
        espera_endereco = self._has_pending_delivery_address_session()
        espera_observacao = self._has_pending_notes_session()
        if not (espera_endereco or espera_observacao):
            return False

        try:
            from apps.automation.services.triagem import Intencao, triar

            # O estado já era conhecido aqui e era jogado fora: `triar` era
            # chamado sem `esperando`, no escuro. É desempate, não atalho.
            esperando = 'endereco' if espera_endereco else 'observacao'

            # O classificador NIM entra SÓ na observação. É ali que a dúvida
            # custa uma venda — "Quero salada" virou "✅ Anotado: Quero salada"
            # e fechou R$ 20 no lugar de R$ 100. No estado de endereço o
            # cliente está digitando um endereço: o catálogo não casa nada, a
            # resposta determinística já está certa, e perguntar ao modelo
            # seria uma ida à rede por endereço digitado sem mudar decisão.
            decisao = triar(
                texto, store=self.store, esperando=esperando,
                classificador=_classificador() if espera_observacao else None,
            )
            return decisao.intencao is not Intencao.ITEM
        except Exception as exc:
            # Triagem quebrada não pode soltar o cliente do checkout: o
            # comportamento antigo (capturar) é o seguro aqui.
            logger.warning('[unified] triagem falhou no portão do checkout: %s', exc)
            return True

    def _has_pending_delivery_address_session(self) -> bool:
        """Return True when this customer has an order waiting for delivery address.

        A consulta mora em `fluxos_do_bot` porque o webhook precisa da MESMA
        resposta antes de deixar a localização passar pelo modo humano.
        """
        from apps.automation.services.fluxos_do_bot import espera_endereco

        return espera_endereco(self.conversation, company=self.company, store=self.store)

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

    def _get_active_session(self) -> Optional[CustomerSession]:
        """Return the active CustomerSession for this conversation, or None."""
        if not self.conversation:
            return None
        phone_number = self.conversation.phone_number
        sessions = CustomerSession.objects.filter(phone_number=phone_number)
        if self.company:
            sessions = sessions.filter(company=self.company)
        return sessions.filter(
            status__in=['active', 'cart_created', 'checkout', 'payment_pending']
        ).order_by('-updated_at').first()

    def _increment_dead_end(self) -> int:
        """Increment consecutive-unresolved counter in session cart_data. Returns new count."""
        try:
            session = self._get_active_session()
            if not session:
                return 0
            count = (session.cart_data or {}).get('_dead_end_count', 0) + 1
            data = dict(session.cart_data or {})
            data['_dead_end_count'] = count
            CustomerSession.objects.filter(pk=session.pk).update(cart_data=data)
            return count
        except Exception as exc:
            logger.warning('[unified] dead_end increment failed: %s', exc)
            return 0

    def _reset_dead_end(self) -> None:
        """Reset dead-end counter when a message resolves successfully."""
        try:
            session = self._get_active_session()
            if not session:
                return
            if (session.cart_data or {}).get('_dead_end_count', 0) > 0:
                data = dict(session.cart_data or {})
                data['_dead_end_count'] = 0
                CustomerSession.objects.filter(pk=session.pk).update(cart_data=data)
        except Exception as exc:
            logger.warning('[unified] dead_end reset failed: %s', exc)

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
        from apps.automation.services.fluxos_do_bot import eh_fluxo_do_bot

        # Fonte única com o webhook_service: esta lista já foi escrita duas
        # vezes e as duas divergiram — o webhook liberava `rating_` e aqui
        # engolia, então o 5★ da cliente virava mensagem de último recurso.
        if eh_fluxo_do_bot((interactive_reply or {}).get('id')):
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

        if getattr(result, 'suppress', False):
            return self._suppressed(f'{intent.value}_silent')

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
            service = LangGraphService(self.agent)

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
            # Suppress LLM internal errors that leak to the user
            _err_indicators = ('não foi possível encontrar', 'nao foi possivel encontrar',
                               'função que atenda', 'funcao que atenda', 'ferramenta.*não encontrada')
            import re as _re
            if any(_re.search(p, response_text.lower()) for p in _err_indicators):
                logger.warning('[unified] LLM leaked tool error — suppressing: %s', response_text[:120])
                response_text = ''
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
        """Invólucro que PERSISTE o que o pipeline já sabe.

        A tela "Intenções" do painel ficou permanentemente vazia porque
        `IntentLog.objects.create` não existia em lugar nenhum do código: o
        modelo, a API e a tela foram feitos, e a escrita nunca. O pipeline
        calcula intenção, origem, handler e duração a cada mensagem e emitia
        isso só num log de texto, que morre no stdout do container.

        O log fica AQUI, e não dentro do processamento, porque
        `_processar_mensagem` tem dezenas de `return` (atalho de localização,
        checkout pendente, modo humano, erro…). Gravar em cada um garantiria
        que algum ficasse de fora — que é como uma tela nasce meio vazia e
        deixa de merecer confiança.
        """
        # O botão "Respostas Automáticas" do painel precisa DESLIGAR o bot.
        # Ele existia, o lojista mexia, e o backend nunca lia: a única
        # ocorrência de `auto_reply_enabled` fora do model era um eco num
        # payload de status. Quem queria assumir a conversa desligava o botão e
        # o bot continuava respondendo por cima.
        #
        # A trava fica AQUI pelo mesmo motivo que o log de intenção: lá dentro
        # há dezenas de `return` e algum ramo escaparia.
        #
        # Desligado, não processa — não é só "não responde". Quem desligou vai
        # atender à mão, e um bot mantendo carrinho por baixo do atendente é
        # pior do que bot nenhum. A mensagem do cliente continua sendo gravada
        # na caixa de entrada, que é trabalho do webhook.
        #
        # Ausência de perfil ou do campo NÃO cala o bot: calar por omissão
        # seria um estrago maior que o defeito.
        perfil = getattr(self, 'company', None)
        if perfil is not None and getattr(perfil, 'auto_reply_enabled', True) is False:
            logger.info(
                'Resposta automática desligada no painel para o perfil %s — '
                'mensagem não processada.', getattr(perfil, 'id', '?'),
            )
            return None

        import time as _time
        inicio = _time.monotonic()
        resposta = self._processar_mensagem(
            message_text,
            interactive_reply=interactive_reply,
            location_data=location_data,
        )
        self._registrar_intencao(
            message_text=message_text,
            resposta=resposta,
            duracao_ms=round((_time.monotonic() - inicio) * 1000, 1),
        )
        return resposta

    def _registrar_intencao(self, message_text, resposta, duracao_ms) -> None:
        """Grava a linha da tela "Intenções". Nunca estoura para o chamador."""
        from apps.automation.models import IntentLog

        if not getattr(self, 'company', None):
            return
        try:
            fonte = getattr(getattr(resposta, 'source', None), 'value', None) or 'sem_resposta'
            meta = getattr(resposta, 'metadata', None) or {}
            telefone = (
                getattr(self, 'phone_number', None)
                or getattr(getattr(self, 'conversation', None), 'phone_number', '')
                or ''
            )
            IntentLog.objects.create(
                company=self.company,
                conversation=getattr(self, 'conversation', None),
                phone_number=telefone,
                message_text=message_text or '',
                # Sem resposta é informação, não ausência dela: é o caso que a
                # dona precisa ver para saber onde o bot está calando.
                intent_type=str(meta.get('intent') or ('sem_resposta' if resposta is None else fonte)),
                method=(
                    IntentLog.MethodType.LLM if fonte == 'llm'
                    else IntentLog.MethodType.NONE if resposta is None
                    else IntentLog.MethodType.REGEX
                ),
                confidence=float(meta.get('confidence') or 0.0),
                handler_used=str(meta.get('handler') or ''),
                response_text=(getattr(resposta, 'content', '') or ''),
                response_type=(
                    IntentLog.ResponseType.INTERACTIVE
                    if getattr(resposta, 'interactive_type', None) or getattr(resposta, 'buttons', None)
                    else IntentLog.ResponseType.TEXT
                ),
                processing_time_ms=duracao_ms,
                entities=(meta.get('entities') or {}),
                metadata={'source': fonte},
            )
        except Exception:
            # Observabilidade nunca pode custar a resposta ao cliente.
            logger.warning('[unified] falha ao gravar IntentLog', exc_info=True)

    def _processar_mensagem(
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

        # ── Modo restrito: fluxos de bot (cliques/listas/localização) ficam
        # desligados; só intents da allow-list respondem, mais abaixo. ──
        # Toggle do lojista: bot não fecha pedidos → cliques de fluxo de pedido
        # e localização viram redirecionamento pro site (antes do modo restrito,
        # pra dar resposta útil em vez de silêncio).
        if not self._bot_order_enabled():
            reply_id = (interactive_reply or {}).get('id', '')
            is_order_click = bool(interactive_reply) and not (
                reply_id in self.NON_ORDER_REPLY_IDS or reply_id.startswith('track_')
            )
            if is_order_click or location_data:
                return self._order_disabled_response()

        _restricted = self._allowed_intents()
        if _restricted is not None and (interactive_reply or location_data):
            return self._suppressed('interactive_or_location')

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
            # Sticker/mídia sem texto: não responde "não entendi" — silêncio.
            return self._suppressed('empty_message')

        normalized = message_text.strip()

        # Checkout state has priority over intent detection/LLM.
        # Example: after asking for preparation notes, "nao" means "no notes",
        # not a general negative answer for the LLM to reinterpret.
        # Exception: cancel commands must escape the checkout handler so they reach CANCEL_ORDER.
        _early_cancel = bool(re.search(
            r'(?i)^(cancela|cancelo|cancelar|cancele|não quero mais|nao quero mais'
            r'|esquece|esquece isso|esquece a[ií]|deixa pra l[áa]|larga m[ãa]o|larga'
            r'|desisti|desistir|n[ãa]o quero|pode cancelar|pode esquecer)\.?$',
            normalized,
        ))
        # Pedido de atendente também escapa do checkout: cliente presa no
        # loop de endereço precisa conseguir chamar um humano.
        _early_human = bool(re.search(
            r'(?i)(atendente|atendimento humano|falar com (um[a]? )?(pessoa|humano|algu[ée]m|gente)'
            r'|quero falar com|chama algu[ée]m|ajuda humana|suporte)',
            normalized,
        ))
        # Combo em montagem: "1, 3, 5" só faz sentido para quem perguntou os
        # sabores. Vem ANTES da detecção de intenção porque um número solto não
        # casa com nada e cairia em UNKNOWN — o cliente responderia a pergunta
        # do bot e receberia "não entendi".
        #
        # Depois do cancelamento e do pedido de atendente, de propósito: quem
        # quer desistir ou falar com gente não pode ficar preso escolhendo
        # salada.
        if not _early_cancel and not _early_human:
            resposta_combo = self._responder_montagem_de_combo(normalized)
            if resposta_combo is not None:
                return resposta_combo

        if not _early_cancel and not _early_human and _restricted is None and self._estado_deve_capturar(normalized):
            from apps.whatsapp.intents.handlers import UnknownHandler
            try:
                handler = UnknownHandler(self.account, self.conversation, self.company)
                if self.store:
                    handler.store = self.store
                result = handler.handle({'original_message': normalized})
                if result and not result.requires_llm:
                    _ms = round((time.monotonic() - _t0) * 1000, 1)
                    logger.info(
                        '[unified] pending checkout text handler (%.0fms)',
                        _ms,
                        extra={
                            'unified.source': 'handler',
                            'unified.intent': 'pending_checkout_text',
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
                            metadata={'intent': 'pending_checkout_text'},
                            interactive_type=result.interactive_type,
                            interactive_data=interactive_data,
                        )
                    if result.response_text not in {None, '', 'BUTTONS_SENT', 'LIST_SENT', 'INTERACTIVE_SENT'}:
                        return UnifiedResponse(
                            content=result.response_text,
                            source=ResponseSource.HANDLER,
                            metadata={'intent': 'pending_checkout_text'},
                        )
            except Exception as exc:
                logger.error('[unified] pending checkout text handler failed: %s', exc, exc_info=True)

        intent_data = self.detector.detect(normalized.lower())
        intent = intent_data.get('intent', IntentType.UNKNOWN)

        if intent == IntentType.UNKNOWN and self._message_matches_catalog_product(normalized):
            intent = IntentType.PRODUCT_MENTION
            intent_data['intent'] = intent
            intent_data['method'] = 'catalog_match'
            intent_data['confidence'] = 0.98

        if _restricted is not None and intent.value not in _restricted:
            return self._suppressed(intent.value)

        if intent.value in self.ORDER_FLOW_INTENT_VALUES and not self._bot_order_enabled():
            return self._order_disabled_response()

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
            self._reset_dead_end()
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
            self._reset_dead_end()
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
                self._reset_dead_end()
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

        # 4. Fallback — detecta loop de dead-end: 3 msgs consecutivas sem resolução → handoff
        if intent == IntentType.UNKNOWN:
            dead_end_count = self._increment_dead_end()
            if dead_end_count >= 3:
                handoff_response = self._run_handler({'intent': IntentType.HUMAN_HANDOFF, 'original_message': normalized})
                if handoff_response is not None:
                    self._reset_dead_end()
                    _ms = round((time.monotonic() - _t0) * 1000, 1)
                    logger.info(
                        '[unified] dead_end handoff triggered (%.0fms) count=%d',
                        _ms, dead_end_count,
                        extra={'unified.source': 'handler', 'unified.intent': 'dead_end_handoff',
                               'unified.duration_ms': _ms, 'unified.store_id': _store_id},
                    )
                    return handoff_response

        _ms = round((time.monotonic() - _t0) * 1000, 1)
        logger.warning(
            '[unified] fallback response (%.0fms) intent=%s — nenhum provider respondeu',
            _ms, intent.value,
            extra={'unified.source': 'fallback', 'unified.intent': intent.value,
                   'unified.duration_ms': _ms, 'unified.store_id': _store_id},
        )
        self.stats['fallback'] += 1
        _fallback_buttons = [
            {'id': 'view_menu', 'title': '📋 Cardápio'},
            {'id': 'contact_support', 'title': '👤 Atendente'},
        ]
        return UnifiedResponse(
            content='Como posso te ajudar? 👇',
            source=ResponseSource.FALLBACK,
            metadata={
                'intent': intent.value,
                'unified.duration_ms': _ms,
            },
            interactive_type='buttons',
            interactive_data={'buttons': _fallback_buttons},
        )

    def _por_no_carrinho(self, item: dict) -> str:
        """Acrescenta a linha aos itens pendentes e devolve o resumo do carrinho.

        Usa o MESMO `pending_order_items` dos produtos: é ele que a finalização
        lê para criar o pedido, e `create_order_from_whatsapp` já aceita linha
        de combo (`combo_id` + `group_selections`) desde 10/ago. Guardar combo
        num lugar separado criaria dois carrinhos para o mesmo cliente.
        """
        from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler

        try:
            gerente = self._get_session_manager()
            itens = gerente.get_pending_order_items() or []
            itens.append(item)
            gerente.save_pending_order_items(itens)
        except Exception as exc:
            logger.warning('[unified] não consegui pôr o combo no carrinho: %s', exc)
            return 'Não consegui adicionar ao pedido agora — me chama que eu resolvo.'

        try:
            handler = InteractiveReplyHandler(self.account, self.conversation, self.company)
            if self.store:
                handler.store = self.store
            return handler._texto_do_carrinho(itens)
        except Exception as exc:
            logger.warning('[unified] resumo do carrinho falhou: %s', exc)
            return 'Adicionado ao seu pedido! 🛒'

    def _responder_montagem_de_combo(self, texto: str):
        """Continua a escolha de sabores de um combo, se houver uma em curso.

        Devolve None quando não há montagem aberta — o fluxo normal segue.
        """
        from apps.automation.services.montagem_de_combo import (
            CHAVE, Grupo, Opcao, grupos_do_combo, responder,
        )

        try:
            gerente = self._get_session_manager()
            sessao = gerente.get_or_create_session()
            estado = (sessao.context or {}).get(CHAVE)
            if not estado:
                return None

            from apps.stores.models import StoreCombo

            combo = StoreCombo.objects.filter(
                id=estado.get('combo_id'), store=self.store,
            ).first()
            if combo is None:
                sessao.update_context(CHAVE, None)
                return None

            grupos = grupos_do_combo(combo)
            if not grupos:
                sessao.update_context(CHAVE, None)
                return None

            r = responder(estado, texto, grupos[0])
            sessao.update_context(CHAVE, r.estado)

            texto_final = r.texto
            if r.item is not None:
                # A escolha confirmada vira linha do carrinho AGORA. Sem isto o
                # bot conduzia a montagem inteira, dizia "Fechado!" e o combo
                # sumia — a conversa toda terminava em nada.
                texto_final = f'{r.texto}\n\n{self._por_no_carrinho(r.item)}'

            return UnifiedResponse(
                content=texto_final,
                source=ResponseSource.HANDLER,
                metadata={'intent': 'combo_em_montagem'},
            )
        except Exception as exc:
            # Montagem quebrada não pode engolir a mensagem do cliente: sem o
            # None aqui, ele ficaria mudo no meio da escolha.
            logger.warning('[unified] montagem de combo falhou: %s', exc)
            return None





#: Instância única do classificador — criar um por mensagem recriaria o cliente
#: HTTP a cada chamada.
_CLASSIFICADOR = None


def _classificador():
    """Devolve o classificador NIM, ou None quando desligado.

    A chave de desligamento existe porque isto é uma chamada de rede no caminho
    do cliente. Se a NVIDIA degradar, `BOT_CLASSIFICADOR=0` tira do caminho sem
    deploy — e a triagem determinística continua respondendo.
    """
    import os

    if os.getenv('BOT_CLASSIFICADOR', '1') in ('0', 'false', 'False'):
        return None

    global _CLASSIFICADOR
    if _CLASSIFICADOR is None:
        from apps.automation.services.classificador import ClassificadorNIM

        _CLASSIFICADOR = ClassificadorNIM()
    return _CLASSIFICADOR





LLMOrchestratorService = UnifiedService
