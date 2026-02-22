"""
Unified Automation Service - Simplificado e Funcional

Fluxo:
1. Detecta intent (regex rápido)
2. Busca template apropriado no banco (AutoMessage)
3. Se encontrar template com botões, usa ele
4. Se não, chama LLM para gerar resposta
5. Se LLM falhar, usa fallback
"""
import logging
import time
import json
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from apps.agents.models import Agent
from apps.agents.services import LangchainService
from apps.automation.models import CompanyProfile, AutoMessage, CustomerSession, IntentLog
from apps.whatsapp.intents.detector import IntentDetector, IntentType
from apps.whatsapp.intents.handlers import get_handler, HandlerResult
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService

logger = logging.getLogger(__name__)


class ResponseSource(Enum):
    """Origem da resposta."""
    TEMPLATE = "template"      # Usou template do banco
    LLM = "llm"                # Resposta da LLM
    HANDLER = "handler"        # Usou handler
    FALLBACK = "fallback"      # Fallback


@dataclass
class UnifiedResponse:
    """Resposta padronizada."""
    content: str
    source: ResponseSource
    buttons: Optional[List[Dict[str, str]]] = None
    header: Optional[str] = None
    footer: Optional[str] = None
    metadata: Optional[dict] = None


class UnifiedService:
    """
    Serviço unificado simplificado.
    Prioriza templates do banco, depois LLM.
    """
    
    def __init__(self, account, conversation, debug: bool = False, use_llm: bool = True):
        self.account = account
        self.conversation = conversation
        self.debug = debug
        self.use_llm = use_llm  # Mantido para compatibilidade
        self.detector = IntentDetector()
        self.company = self._get_company()
        self.stats = {'template': 0, 'llm': 0, 'handler': 0, 'fallback': 0}
    
    def _get_company(self) -> Optional[CompanyProfile]:
        """Busca CompanyProfile da conta."""
        try:
            return CompanyProfile.objects.get(account=self.account, is_active=True)
        except CompanyProfile.DoesNotExist:
            return None
    
    def _get_store(self):
        """Busca Store associada."""
        if self.company and hasattr(self.company, 'store') and self.company.store_id:
            return self.company.store
        # Fallback: busca store 'pastita'
        from apps.stores.models import Store
        return Store.objects.filter(slug='pastita').first()
    
    def _map_intent_to_event(self, intent: IntentType) -> str:
        """Mapeia intent para event_type do AutoMessage."""
        mapping = {
            IntentType.GREETING: 'welcome',
            IntentType.MENU_REQUEST: 'menu',
            IntentType.PRODUCT_INQUIRY: 'menu',
            IntentType.PRODUCT_MENTION: 'menu',
            IntentType.ADD_TO_CART: 'cart_created',
            IntentType.VIEW_CART: 'cart_created',
            IntentType.CREATE_ORDER: 'order_received',
            IntentType.ORDER_STATUS: 'order_confirmed',
            IntentType.PAYMENT_STATUS: 'payment_confirmed',
            IntentType.REQUEST_PIX: 'pix_generated',
            IntentType.CONFIRM_PAYMENT: 'payment_confirmed',
            IntentType.BUSINESS_HOURS: 'business_hours',
            IntentType.LOCATION: 'business_hours',
            IntentType.HELP: 'faq',
            IntentType.UNKNOWN: 'welcome',
        }
        return mapping.get(intent, 'custom')
    
    def _get_template_for_intent(self, intent: IntentType) -> Optional[AutoMessage]:
        """Busca template no banco baseado na intent."""
        if not self.company:
            return None
        
        event_type = self._map_intent_to_event(intent)
        
        template = AutoMessage.objects.filter(
            company=self.company,
            event_type=event_type,
            is_active=True
        ).order_by('priority').first()
        
        return template
    
    def _build_context(self, intent_data: Dict, session_data: Dict) -> str:
        """Constrói contexto para LLM."""
        parts = []
        
        # Dados da loja
        store = self._get_store()
        if store:
            parts.append(f"Loja: {store.name}")
            parts.append(f"Telefone: {store.whatsapp_number or 'N/A'}")
        
        # Intent
        intent = intent_data.get('intent')
        if intent:
            parts.append(f"Intenção: {intent.value}")
        
        # Carrinho/Pedido
        if session_data.get('has_cart'):
            parts.append(f"Carrinho: R$ {session_data.get('cart_total', 0):.2f}")
        if session_data.get('has_order'):
            parts.append(f"Pedido: {session_data.get('order_id', 'N/A')}")
        
        # Produtos disponíveis
        if store:
            from apps.stores.models import StoreProduct
            products = StoreProduct.objects.filter(store=store, is_active=True)[:5]
            if products:
                parts.append("\nProdutos disponíveis:")
                for p in products:
                    parts.append(f"- {p.name}: R$ {p.price:.2f}")
        
        return "\n".join(parts)
    
    def _get_session_data(self) -> Dict:
        """Busca dados da sessão do cliente."""
        phone = self.conversation.phone_number
        
        # Busca CustomerSession
        session = CustomerSession.objects.filter(
            phone_number=phone,
            status__in=['active', 'cart_created', 'checkout', 'payment_pending']
        ).order_by('-updated_at').first()
        
        if session:
            return {
                'has_cart': bool(session.cart_data),
                'cart_total': float(session.cart_total or 0),
                'cart_items_count': session.cart_items_count,
                'has_order': bool(session.order_id),
                'order_id': session.order_id,
                'pix_pending': bool(session.pix_code and not session.payment_id),
            }
        
        return {'has_cart': False, 'cart_total': 0, 'cart_items_count': 0}
    
    def _call_llm(self, message: str, context: str) -> Optional[str]:
        """Chama LLM para gerar resposta."""
        try:
            agent = Agent.objects.filter(status='active').first()
            if not agent:
                return None
            
            service = LangchainService(agent)
            
            # Busca session_id
            from apps.agents.models import AgentConversation
            agent_conv = AgentConversation.objects.filter(
                agent=agent,
                phone_number=self.conversation.phone_number
            ).order_by('-last_message_at').first()
            
            session_id = str(agent_conv.session_id) if agent_conv else None
            
            # Mensagem enriquecida
            enriched = f"{context}\n\n---\n\nCliente: {message}"
            
            result = service.process_message(
                message=enriched,
                session_id=session_id,
                phone_number=self.conversation.phone_number,
                conversation_id=str(self.conversation.id)
            )
            
            return result.get('response', '')
        except Exception as e:
            logger.error(f"[Unified] LLM error: {e}")
            return None
    
    def _render_template(self, template: AutoMessage, session_data: Dict) -> str:
        """Renderiza template com variáveis."""
        text = template.message_text
        
        # Variáveis básicas
        text = text.replace('{customer_name}', self.conversation.contact_name or 'Cliente')
        text = text.replace('{company_name}', self.company.company_name if self.company else 'Nossa Loja')
        text = text.replace('{phone}', self.conversation.phone_number)
        
        # Carrinho
        text = text.replace('{cart_total}', f"R$ {session_data.get('cart_total', 0):.2f}")
        text = text.replace('{cart_items}', str(session_data.get('cart_items_count', 0)))
        
        # Pedido
        text = text.replace('{order_id}', session_data.get('order_id', ''))
        
        return text
    
    def process_message(self, message_text: str) -> UnifiedResponse:
        """
        Processa mensagem do cliente.
        
        Fluxo:
        1. Detecta intent
        2. Tenta usar template do banco
        3. Se não tiver template, chama LLM
        4. Se falhar, usa fallback
        """
        start_time = time.time()
        
        if not message_text or not message_text.strip():
            return UnifiedResponse(
                content="Desculpe, não entendi. Pode repetir?",
                source=ResponseSource.FALLBACK
            )
        
        # 1. Detecta intent
        intent_data = self.detector.detect(message_text.strip().lower())
        intent = intent_data.get('intent', IntentType.UNKNOWN)
        
        if self.debug:
            logger.info(f"[Unified] Intent: {intent.value}")
        
        # 2. Busca template no banco
        template = self._get_template_for_intent(intent)
        
        if template:
            # Usa template do banco
            session_data = self._get_session_data()
            content = self._render_template(template, session_data)
            
            self.stats['template'] += 1
            
            return UnifiedResponse(
                content=content,
                source=ResponseSource.TEMPLATE,
                buttons=template.buttons if template.buttons else None,
                metadata={
                    'template_id': str(template.id),
                    'event_type': template.event_type,
                    'intent': intent.value,
                }
            )
        
        # 3. Se não tem template, chama LLM
        session_data = self._get_session_data()
        context = self._build_context(intent_data, session_data)
        
        llm_response = self._call_llm(message_text, context)
        
        if llm_response:
            self.stats['llm'] += 1
            
            return UnifiedResponse(
                content=llm_response,
                source=ResponseSource.LLM,
                metadata={'intent': intent.value}
            )
        
        # 4. Fallback
        self.stats['fallback'] += 1
        
        return UnifiedResponse(
            content="Desculpe, estou com dificuldades no momento. Um atendente humano pode te ajudar?",
            source=ResponseSource.FALLBACK
        )


# Alias para compatibilidade
LLMOrchestratorService = UnifiedService
