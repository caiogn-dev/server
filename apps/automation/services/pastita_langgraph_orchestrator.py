"""
Pastita LangGraph Orchestrator - Orquestrador principal usando LangGraph.

Este módulo integra o grafo LangGraph com os models e services existentes,
fornecendo uma interface unificada para processamento de mensagens WhatsApp.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

from langchain_core.messages import HumanMessage
from django.utils import timezone

from apps.automation.graphs.pastita_graph import (
    get_pastita_graph, create_initial_state, PastitaState,
    ConversationState, IntentType, ContextSource
)
from .pastita_tools import PASTITA_TOOLS

logger = logging.getLogger(__name__)


class LangGraphOrchestrator:
    """
    Orquestrador inteligente usando LangGraph.
    
    Combina:
    - LangGraph para fluxo de estados
    - Tools do sistema para ações precisas
    - Decisão contextual entre handler/automessage/llm
    """
    
    def __init__(
        self,
        account,
        conversation,
        company,
        store,
        debug: bool = False
    ):
        """
        Inicializa o orquestrador.
        
        Args:
            account: WhatsAppAccount
            conversation: Conversation
            company: CompanyProfile
            store: Store
            debug: Se True, loga informações detalhadas
        """
        self.account = account
        self.conversation = conversation
        self.company = company
        self.store = store
        self.debug = debug
        
        # Obtém ou cria sessão
        self.session = self._get_or_create_session()
        
        # Carrega estado do grafo
        self.graph_state = self._load_graph_state()
        
        # Obtém instância do grafo
        self.graph = get_pastita_graph()
        
        if self.debug:
            logger.info(f"[LangGraphOrchestrator] Initialized for {conversation.phone_number}")
    
    def _get_or_create_session(self):
        """Obtém ou cria sessão do cliente."""
        from apps.automation.models import CustomerSession
        
        session, created = CustomerSession.objects.get_or_create(
            phone_number=self.conversation.phone_number,
            company=self.company,
            defaults={
                'session_id': f"lg_{self.conversation.phone_number}_{int(timezone.now().timestamp())}",
                'status': 'active',
                'customer_name': self.conversation.contact_name or 'Cliente',
            }
        )
        
        if created and self.debug:
            logger.info(f"[LangGraphOrchestrator] Created new session: {session.session_id}")
        
        return session
    
    def _load_graph_state(self) -> PastitaState:
        """Carrega estado do grafo do banco de dados."""
        # Converte cart_data para formato do grafo
        cart_items = []
        if self.session.cart_data and 'items' in self.session.cart_data:
            cart_items = self.session.cart_data['items']
        
        # Converte order_data
        order_data = {
            'order_id': str(self.session.order_id) if self.session.order_id else None,
            'order_number': None,
            'payment_method': self.session.payment_method or None,
            'delivery_method': self.session.delivery_method or None,
            'delivery_address': self.session.delivery_address or None,
            'delivery_fee': float(self.session.delivery_fee) if self.session.delivery_fee else None,
            'subtotal': float(self.session.cart_total) if self.session.cart_total else 0.0,
            'total': float(self.session.cart_total) if self.session.cart_total else 0.0,
        }
        
        # Busca order_number se tiver order_id
        if order_data['order_id']:
            from apps.stores.models import StoreOrder
            order = StoreOrder.objects.filter(id=order_data['order_id']).first()
            if order:
                order_data['order_number'] = order.order_number
                order_data['total'] = float(order.total)
        
        state = create_initial_state(
            session_id=str(self.session.id),
            phone_number=self.conversation.phone_number,
            company_id=str(self.company.id),
            store_id=str(self.store.id),
            account_id=str(self.account.id)
        )
        
        # Atualiza com dados da sessão
        state['cart'] = {
            'items': cart_items,
            'total': float(self.session.cart_total) if self.session.cart_total else 0.0
        }
        state['order_data'] = order_data
        
        # Mapeia status da sessão para estado do grafo
        status_map = {
            'active': ConversationState.GREETING,
            'cart_created': ConversationState.CART,
            'awaiting_delivery_method': ConversationState.DELIVERY_METHOD,
            'awaiting_address': ConversationState.ADDRESS,
            'awaiting_payment_method': ConversationState.PAYMENT_METHOD,
            'checkout': ConversationState.CHECKOUT,
            'payment_pending': ConversationState.AWAITING_PAYMENT,
            'order_placed': ConversationState.ORDER_CONFIRMED,
        }
        state['current_state'] = status_map.get(self.session.status, ConversationState.GREETING)
        
        return state
    
    def _save_graph_state(self, state: PastitaState):
        """Salva estado do grafo no banco de dados."""
        # Atualiza carrinho
        self.session.cart_data = {
            'items': state['cart'].get('items', [])
        }
        self.session.cart_total = Decimal(str(state['cart'].get('total', 0)))
        self.session.cart_items_count = sum(
            item.get('quantity', 1) for item in state['cart'].get('items', [])
        )
        
        # Atualiza dados do pedido
        order_data = state['order_data']
        if order_data.get('order_id'):
            self.session.order_id = order_data['order_id']
        if order_data.get('payment_method'):
            self.session.payment_method = order_data['payment_method']
        if order_data.get('delivery_method'):
            self.session.delivery_method = order_data['delivery_method']
        if order_data.get('delivery_address'):
            self.session.delivery_address = order_data['delivery_address']
        if order_data.get('delivery_fee'):
            self.session.delivery_fee = Decimal(str(order_data['delivery_fee']))
        
        # Mapeia estado do grafo para status da sessão
        state_map = {
            ConversationState.GREETING: 'active',
            ConversationState.MENU: 'active',
            ConversationState.CART: 'cart_created',
            ConversationState.DELIVERY_METHOD: 'awaiting_delivery_method',
            ConversationState.ADDRESS: 'awaiting_address',
            ConversationState.PAYMENT_METHOD: 'awaiting_payment_method',
            ConversationState.CHECKOUT: 'checkout',
            ConversationState.AWAITING_PAYMENT: 'payment_pending',
            ConversationState.ORDER_CONFIRMED: 'order_placed',
        }
        self.session.status = state_map.get(state['current_state'], self.session.status)
        
        # Atualiza timestamp
        self.session.last_activity_at = timezone.now()
        
        self.session.save()
    
    def process_message(self, message_text: str) -> Dict[str, Any]:
        """
        Processa uma mensagem do usuário.
        
        Args:
            message_text: Texto da mensagem recebida
        
        Returns:
            Dict com response_text, buttons, e metadata
        """
        import time
        start_time = time.time()
        
        if self.debug:
            logger.info(f"[LangGraphOrchestrator] Processing: {message_text[:50]}...")
        
        # Adiciona mensagem ao estado
        self.graph_state['messages'].append(HumanMessage(content=message_text))
        
        # Executa o grafo
        try:
            result = self.graph.invoke(self.graph_state)
            
            # Atualiza estado local
            self.graph_state = result
            
            # Salva no banco
            self._save_graph_state(result)
            
            # Calcula tempo de processamento
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Salva log de intenção
            self._save_intent_log(message_text, result, processing_time_ms)
            
            response = {
                'response_text': result.get('response_text', ''),
                'buttons': result.get('response_buttons'),
                'current_state': result.get('current_state'),
                'intent': result.get('last_intent'),
                'context_source': result.get('context_source'),
            }
            
            if self.debug:
                logger.info(f"[LangGraphOrchestrator] Response: {response['response_text'][:50]}...")
                logger.info(f"[LangGraphOrchestrator] State: {response['current_state']}")
            
            return response
            
        except Exception as e:
            logger.exception(f"[LangGraphOrchestrator] Error: {e}")
            return {
                'response_text': "Desculpe, tive um problema. Tente novamente ou digite 'atendente'.",
                'buttons': None,
                'current_state': ConversationState.ERROR,
                'intent': IntentType.UNKNOWN,
                'context_source': ContextSource.FALLBACK,
            }
    
    def _save_intent_log(self, message_text: str, result: Dict[str, Any], processing_time_ms: int):
        """
        Salva log de intenção para analytics.
        
        Args:
            message_text: Texto da mensagem recebida
            result: Resultado do processamento
            processing_time_ms: Tempo de processamento em ms
        """
        try:
            from apps.automation.models import IntentLog
            
            # Obtém dados do resultado
            intent = result.get('last_intent')
            context_source = result.get('context_source')
            response_text = result.get('response_text', '')
            
            # Determina o método baseado na fonte do contexto
            method_map = {
                'handler': IntentLog.MethodType.REGEX,  # Handler usa regex/patterns
                'automessage': IntentLog.MethodType.REGEX,  # AutoMessage é baseado em regras
                'llm': IntentLog.MethodType.LLM,
                'fallback': IntentLog.MethodType.NONE,
            }
            method = method_map.get(str(context_source).lower(), IntentLog.MethodType.REGEX)
            
            # Determina tipo de resposta
            response_type = IntentLog.ResponseType.TEXT
            if result.get('response_buttons'):
                response_type = IntentLog.ResponseType.BUTTONS
            
            # Cria o log
            IntentLog.objects.create(
                company=self.company,
                message=None,  # Pode ser atualizado se tiver referência à mensagem
                conversation=self.conversation,
                phone_number=self.conversation.phone_number,
                message_text=message_text[:1000],
                intent_type=str(intent) if intent else 'unknown',
                method=method,
                confidence=0.95 if method == IntentLog.MethodType.REGEX else 0.80,
                handler_used=str(context_source) if context_source else '',
                response_text=response_text[:2000],
                response_type=response_type,
                processing_time_ms=processing_time_ms,
                entities=result.get('entities', {}),
                metadata={
                    'current_state': str(result.get('current_state')),
                    'cart_items_count': len(result.get('cart', {}).get('items', [])),
                }
            )
            
            if self.debug:
                logger.info(f"[LangGraphOrchestrator] Intent log saved: {intent} ({method})")
                
        except Exception as e:
            logger.error(f"[LangGraphOrchestrator] Error saving intent log: {e}")
    
    def get_state(self) -> Dict[str, Any]:
        """Retorna estado atual da conversa."""
        return {
            'current_state': self.graph_state.get('current_state'),
            'cart': self.graph_state.get('cart'),
            'order_data': self.graph_state.get('order_data'),
            'last_intent': self.graph_state.get('last_intent'),
            'error_count': self.graph_state.get('error_count', 0),
        }
    
    def reset(self):
        """Reseta a conversa."""
        from .pastita_tools import clear_cart
        
        # Limpa carrinho
        clear_cart.invoke({'session_id': str(self.session.id)})
        
        # Reseta estado
        self.graph_state = create_initial_state(
            session_id=str(self.session.id),
            phone_number=self.conversation.phone_number,
            company_id=str(self.company.id),
            store_id=str(self.store.id),
            account_id=str(self.account.id)
        )
        
        # Reseta sessão
        self.session.status = 'active'
        self.session.cart_data = {'items': []}
        self.session.cart_total = 0
        self.session.cart_items_count = 0
        self.session.order_id = None
        self.session.payment_method = ''
        self.session.delivery_method = ''
        self.session.delivery_address = ''
        self.session.delivery_fee = None
        self.session.save()
        
        if self.debug:
            logger.info(f"[LangGraphOrchestrator] Reset session: {self.session.session_id}")


class ContextRouter:
    """
    Roteador contextual que decide qual fonte de resposta usar.
    
    Regras:
    1. Se é ação de carrinho/pedido → HANDLER (precisão 100%)
    2. Se tem mensagem automática configurada para o estado → AUTOMESSAGE
    3. Se é pergunta complexa/saudação/dúvida → LLM
    4. Se handler falhou → fallback para LLM
    5. Se estado crítico (checkout, pagamento) → sempre HANDLER
    """
    
    # Intenções que sempre usam handler
    HANDLER_INTENTS = [
        IntentType.ADD_TO_CART,
        IntentType.REMOVE_FROM_CART,
        IntentType.VIEW_CART,
        IntentType.CLEAR_CART,
        IntentType.CREATE_ORDER,
        IntentType.CONFIRM_ORDER,
        IntentType.CANCEL_ORDER,
        IntentType.SELECT_DELIVERY,
        IntentType.SELECT_PICKUP,
        IntentType.REQUEST_PIX,
        IntentType.CONFIRM_PAYMENT,
        IntentType.CHECK_STATUS,
    ]
    
    # Estados críticos que sempre usam handler
    CRITICAL_STATES = [
        ConversationState.CHECKOUT,
        ConversationState.AWAITING_PAYMENT,
        ConversationState.PAYMENT_METHOD,
    ]
    
    def __init__(self, company):
        self.company = company
    
    def route(self, state: PastitaState) -> ContextSource:
        """
        Decide qual fonte de resposta usar.
        
        Args:
            state: Estado atual da conversa
        
        Returns:
            ContextSource indicando a fonte a usar
        """
        intent = state.get('last_intent')
        current_state = state.get('current_state')
        error_count = state.get('error_count', 0)
        
        # Se teve muitos erros, tenta LLM
        if error_count >= 2:
            return ContextSource.LLM
        
        # Estados críticos sempre usam handler
        if current_state in self.CRITICAL_STATES:
            return ContextSource.HANDLER
        
        # Intenções de ação usam handler
        if intent in self.HANDLER_INTENTS:
            return ContextSource.HANDLER
        
        # Verifica se tem mensagem automática configurada
        if self._has_automessage(intent, current_state):
            return ContextSource.AUTOMESSAGE
        
        # Saudações podem usar automessage ou handler
        if intent == IntentType.GREETING:
            return ContextSource.HANDLER  # Por enquanto, handler
        
        # Intenção desconhecida usa LLM
        if intent == IntentType.UNKNOWN:
            return ContextSource.LLM
        
        # Padrão: handler
        return ContextSource.HANDLER
    
    def _has_automessage(self, intent: str, state: str) -> bool:
        """Verifica se existe mensagem automática configurada."""
        from apps.automation.models import AutoMessage
        
        # Mapeia intent/estado para event_type
        event_map = {
            IntentType.GREETING: 'welcome',
            IntentType.MENU_REQUEST: 'menu',
            ConversationState.GREETING: 'welcome',
        }
        
        event_type = event_map.get(intent) or event_map.get(state)
        if not event_type:
            return False
        
        return AutoMessage.objects.filter(
            company=self.company,
            event_type=event_type,
            is_active=True
        ).exists()


def process_whatsapp_message_langgraph(
    account,
    conversation,
    message_text: str,
    debug: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Função utilitária para processar mensagem WhatsApp usando LangGraph.
    
    Args:
        account: WhatsAppAccount
        conversation: Conversation
        message_text: Texto da mensagem
        debug: Se True, loga informações detalhadas
    
    Returns:
        Dict com response_text, buttons, etc. ou None se erro
    """
    try:
        # Busca company e store
        from apps.automation.models import CompanyProfile
        from apps.stores.models import Store
        
        company = None
        store = None
        
        # Tenta obter company da conta
        if hasattr(account, 'company_profile'):
            company = account.company_profile
        
        if not company:
            company = CompanyProfile.objects.filter(
                _company_name__icontains='pastita'
            ).first()
        
        if not company:
            logger.error("[process_whatsapp_message_langgraph] Company not found")
            return None
        
        # Obtém store
        if company.store:
            store = company.store
        else:
            store = Store.objects.filter(slug='pastita').first()
        
        if not store:
            logger.error("[process_whatsapp_message_langgraph] Store not found")
            return None
        
        # Cria orquestrador e processa
        orchestrator = LangGraphOrchestrator(
            account=account,
            conversation=conversation,
            company=company,
            store=store,
            debug=debug
        )
        
        return orchestrator.process_message(message_text)
        
    except Exception as e:
        logger.exception(f"[process_whatsapp_message_langgraph] Error: {e}")
        return None


# Singleton para uso global
_orchestrator_cache = {}


def get_orchestrator(
    account,
    conversation,
    company,
    store,
    debug: bool = False
) -> LangGraphOrchestrator:
    """
    Obtém ou cria orquestrador para uma conversa.
    
    Usa cache para reutilizar orquestradores ativos.
    """
    cache_key = f"{account.id}_{conversation.phone_number}"
    
    if cache_key not in _orchestrator_cache:
        _orchestrator_cache[cache_key] = LangGraphOrchestrator(
            account=account,
            conversation=conversation,
            company=company,
            store=store,
            debug=debug
        )
    
    return _orchestrator_cache[cache_key]
