"""
Unified automation service.

Flow:
1. Detect intent
2. Try deterministic handler
3. Try database template
4. Try LLM with the canonical configured agent
5. Return a small fallback
"""
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from apps.agents.models import AgentConversation
from apps.agents.services import LangchainService
from apps.automation.models import AutoMessage, CustomerSession
from apps.automation.services.context_service import AutomationContextService
from apps.whatsapp.intents.detector import IntentDetector, IntentType
from apps.whatsapp.intents.handlers import get_handler

logger = logging.getLogger(__name__)


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
        def safe_str(value, default=''):
            if value is None:
                return default
            return str(value)

        content = template.message_text
        content = content.replace('{customer_name}', safe_str(self.conversation.contact_name, 'Cliente'))
        content = content.replace('{company_name}', safe_str(self.company.company_name if self.company else None, 'Nossa Loja'))
        content = content.replace('{phone}', safe_str(self.conversation.phone_number))
        content = content.replace('{cart_total}', f"R$ {float(session_data.get('cart_total') or 0):.2f}")
        content = content.replace('{cart_items}', safe_str(session_data.get('cart_items_count'), '0'))
        content = content.replace('{order_id}', safe_str(session_data.get('order_id')))
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

        result = handler.handle(intent_data)
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
        if not self.use_llm or not self.agent:
            return None

        try:
            service = LangchainService(self.agent)
            agent_conversation = AgentConversation.objects.filter(
                agent=self.agent,
                phone_number=self.conversation.phone_number,
            ).order_by('-last_message_at').first()
            session_id = str(agent_conversation.session_id) if agent_conversation else None
            enriched_message = f'{context_text}\n\n---\n\nCliente: {message}' if context_text else message
            result = service.process_message(
                message=enriched_message,
                session_id=session_id,
                phone_number=self.conversation.phone_number,
                conversation_id=str(self.conversation.id),
            )
            return result.get('response', '')
        except Exception as exc:
            logger.error('[Unified] LLM error: %s', exc)
            return None

    def process_message(self, message_text: str) -> UnifiedResponse:
        start_time = time.time()

        if not message_text or not message_text.strip():
            return UnifiedResponse(
                content='Desculpe, nao entendi. Pode repetir?',
                source=ResponseSource.FALLBACK,
            )

        normalized_message = message_text.strip()
        intent_data = self.detector.detect(normalized_message.lower())
        intent = intent_data.get('intent', IntentType.UNKNOWN)

        if self.debug:
            logger.info('[Unified] intent=%s llm=%s store=%s company=%s', intent.value, self.use_llm, getattr(self.store, 'slug', None), getattr(self.company, 'id', None))

        handler_response = self._run_handler(intent_data)
        if handler_response is not None:
            return handler_response

        template = self._get_template_for_intent(intent)
        if template:
            session_data = self._get_session_data()
            self.stats['template'] += 1
            return UnifiedResponse(
                content=self._render_template(template, session_data),
                source=ResponseSource.TEMPLATE,
                buttons=template.buttons if template.buttons else None,
                metadata={
                    'template_id': str(template.id),
                    'event_type': template.event_type,
                    'intent': intent.value,
                    'processing_time_ms': round((time.time() - start_time) * 1000, 2),
                },
                interactive_type='buttons' if template.buttons else None,
                interactive_data={'buttons': template.buttons} if template.buttons else None,
            )

        session_data = self._get_session_data()
        context_text = self._build_context(intent_data, session_data)
        llm_response = self._call_llm(normalized_message, context_text)
        if llm_response:
            self.stats['llm'] += 1
            return UnifiedResponse(
                content=llm_response,
                source=ResponseSource.LLM,
                metadata={
                    'intent': intent.value,
                    'agent_id': str(self.agent.id) if self.agent else None,
                    'processing_time_ms': round((time.time() - start_time) * 1000, 2),
                },
            )

        self.stats['fallback'] += 1
        return UnifiedResponse(
            content='Posso continuar pelo menu, te mostrar o catalogo ou encaminhar voce para um atendente humano.',
            source=ResponseSource.FALLBACK,
            metadata={
                'intent': intent.value,
                'processing_time_ms': round((time.time() - start_time) * 1000, 2),
            },
        )


LLMOrchestratorService = UnifiedService