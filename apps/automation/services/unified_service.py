"""
Unified Automation Service - LLM como Orquestrador Principal

O LLM é sempre ativo e orquestra o sistema:
- Recebe contexto completo (templates, intents, histórico)
- Decide quando usar templates existentes
- Decide quando consultar handlers
- Responde diretamente quando apropriado
"""
import logging
import time
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from apps.agents.models import Agent
from apps.agents.services import LangchainService
from apps.automation.models import CompanyProfile, AutoMessage, CustomerSession, IntentLog
from apps.whatsapp.intents.detector import IntentDetector, IntentType
from apps.whatsapp.intents.handlers import get_handler, HandlerResult
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService

# NOVO: Importar Jasper Templates
from apps.whatsapp.services.templates import JasperTemplates, TemplateRenderer

logger = logging.getLogger(__name__)


class ResponseSource(Enum):
    """Origem da resposta para analytics."""
    AGENT_DIRECT = "agent_direct"      # LLM respondeu diretamente
    AGENT_TEMPLATE = "agent_template"  # LLM usou template
    AGENT_HANDLER = "agent_handler"    # LLM usou handler como ferramenta
    FALLBACK = "fallback"
    NONE = "none"


@dataclass
class UnifiedResponse:
    """Resposta padronizada do sistema unificado."""
    content: str
    source: ResponseSource
    buttons: Optional[list] = None
    media: Optional[dict] = None
    interactive_type: Optional[str] = None
    metadata: Optional[dict] = None


class LLMOrchestratorService:
    """
    Serviço onde o LLM é o orquestrador principal.
    
    O LLM sempre processa a mensagem e decide:
    1. Usar um template existente
    2. Consultar um handler (como ferramenta)
    3. Responder diretamente com seu conhecimento
    
    O LLM recebe como contexto:
    - Templates disponíveis
    - Intent detectada
    - Dados da sessão (carrinho, pedido)
    - Histórico de conversa
    """
    
    def __init__(
        self,
        account,
        conversation,
        use_llm: bool = True,  # Sempre True por padrão
        debug: bool = False
    ):
        self.account = account
        self.conversation = conversation
        self.use_llm = use_llm
        self.debug = debug
        
        # Componentes
        self.detector = IntentDetector(use_llm_fallback=False)
        self.whatsapp_service = WhatsAppAPIService(account)
        
        # Dados da empresa
        self.company = self._get_company()
        
        # Estatísticas
        self.stats = {
            'agent_direct': 0,
            'agent_template': 0,
            'agent_handler': 0,
            'fallbacks': 0,
        }
    
    def _get_company(self) -> Optional[CompanyProfile]:
        """Retorna o CompanyProfile associado à conta."""
        try:
            return CompanyProfile.objects.get(account=self.account, is_active=True)
        except CompanyProfile.DoesNotExist:
            return None
    
    def _get_active_agent(self) -> Optional[Agent]:
        """Retorna o agente ativo para esta conta."""
        if self.company and self.company.default_agent:
            return self.company.default_agent
        if self.account and self.account.default_agent:
            return self.account.default_agent
        return None
    
    def _get_available_templates(self) -> List[Dict]:
        """Retorna templates de automação disponíveis para o contexto."""
        if not self.company:
            return []
        
        templates = AutoMessage.objects.filter(
            company=self.company,
            is_active=True
        ).order_by('event_type', 'priority')
        
        return [
            {
                'event_type': t.event_type,
                'name': t.name,
                'content': t.message_text[:200] + '...' if len(t.message_text) > 200 else t.message_text,
                'has_buttons': bool(t.buttons),
                'source': 'automation',
            }
            for t in templates
        ]
    
    def _get_whatsapp_templates(self) -> List[Dict]:
        """Retorna templates oficiais do WhatsApp aprovados."""
        from apps.whatsapp.models import MessageTemplate
        
        templates = MessageTemplate.objects.filter(
            account=self.account,
            status='approved'
        ).order_by('category', 'name')
        
        return [
            {
                'name': t.name,
                'category': t.category,
                'language': t.language,
                'components': t.components,
                'source': 'whatsapp_template',
            }
            for t in templates
        ]
    
    def _get_jasper_templates(self) -> List[Dict]:
        """Retorna Jasper Templates disponíveis (templates profissionais com botões)."""
        return [
            {
                'name': 'greeting',
                'description': 'Saudação personalizada com botões (Ver Cardápio, Pedido Rápido, Meus Pedidos)',
                'has_buttons': True,
                'buttons': ['📋 Ver Cardápio', '⚡ Pedido Rápido', '📦 Meus Pedidos'],
                'source': 'jasper',
            },
            {
                'name': 'menu_categories',
                'description': 'Menu com categorias em botões',
                'has_buttons': True,
                'buttons': ['⭐ Destaques', '🍕 Pizzas', '🥤 Bebidas'],
                'source': 'jasper',
            },
            {
                'name': 'product_card',
                'description': 'Card de produto com botões de adicionar',
                'has_buttons': True,
                'buttons': ['🛒 Adicionar 1', '🛒 Adicionar 2', '⬅️ Ver Mais'],
                'source': 'jasper',
            },
            {
                'name': 'cart_summary',
                'description': 'Resumo do carrinho com botões de ação',
                'has_buttons': True,
                'buttons': ['💳 Finalizar Pedido', '➕ Adicionar Mais', '🗑️ Limpar'],
                'source': 'jasper',
            },
            {
                'name': 'order_confirmation',
                'description': 'Confirmação de pedido com PIX e botões',
                'has_buttons': True,
                'buttons': ['📋 Copiar Código PIX', '📱 Ver QR Code', '📤 Compartilhar'],
                'source': 'jasper',
            },
            {
                'name': 'payment_confirmed',
                'description': 'Pagamento confirmado com botões de acompanhamento',
                'has_buttons': True,
                'buttons': ['📦 Acompanhar Pedido', '💬 Falar com Atendente'],
                'source': 'jasper',
            },
            {
                'name': 'need_help',
                'description': 'Oferecer ajuda com opções',
                'has_buttons': True,
                'buttons': ['🛒 Fazer Pedido', '📋 Ver Cardápio', '👨‍💼 Falar com Atendente'],
                'source': 'jasper',
            },
            {
                'name': 'fallback',
                'description': 'Mensagem quando não entende com opções',
                'has_buttons': True,
                'buttons': ['📋 Ver Cardápio', '🛒 Fazer Pedido', '❓ Ajuda'],
                'source': 'jasper',
            },
        ]
    
    def _get_session_data(self) -> Dict[str, Any]:
        """Retorna dados da sessão do cliente."""
        if not self.company:
            return {}
        
        session = CustomerSession.objects.filter(
            company=self.company,
            phone_number=self.conversation.phone_number,
            status__in=['active', 'cart_created', 'checkout', 'payment_pending', 'order_placed']
        ).first()
        
        if not session:
            return {}
        
        return {
            'status': session.status,
            'has_cart': bool(session.cart_data),
            'cart_total': float(session.cart_total) if session.cart_total else 0,
            'cart_items_count': session.cart_items_count or 0,
            'has_order': session.order_id is not None,
            'order_id': session.external_order_id,
            'pix_pending': bool(session.pix_code and session.pix_expires_at),
        }
    
    def _build_llm_context(
        self,
        message: str,
        intent_data: Dict,
        templates: List[Dict],
        session_data: Dict
    ) -> str:
        """
        Constrói o contexto completo para o LLM.
        O LLM usa isso para decidir como responder.
        """
        context_parts = []
        
        # 1. Informações sobre templates de automação disponíveis
        automation_templates = [t for t in templates if t.get('source') == 'automation']
        if automation_templates:
            context_parts.append("📋 TEMPLATES DE AUTOMAÇÃO DISPONÍVEIS:")
            for t in automation_templates[:5]:  # Limita a 5 templates
                context_parts.append(f"- [{t['event_type']}] {t['name']}: {t['content'][:100]}")
            context_parts.append("")
            context_parts.append("Você PODE usar esses templates se forem apropriados para a resposta.")
            context_parts.append("")
        
        # 2. Jasper Templates (templates profissionais com botões)
        jasper_templates = self._get_jasper_templates()
        if jasper_templates:
            context_parts.append("🎨 JASPER TEMPLATES (Profissionais com Botões):")
            for t in jasper_templates[:6]:  # Limita a 6
                btn_info = f" [{len(t['buttons'])} botões]" if t.get('has_buttons') else ""
                context_parts.append(f"- [{t['name']}] {t['description'][:80]}{btn_info}")
            context_parts.append("")
            context_parts.append("PREFIRA usar Jasper Templates quando quiser oferecer BOTÕES interativos ao cliente.")
            context_parts.append("")
        
        # 3. Templates oficiais do WhatsApp
        whatsapp_templates = self._get_whatsapp_templates()
        if whatsapp_templates:
            context_parts.append("📱 TEMPLATES OFICIAIS DO WHATSAPP:")
            for t in whatsapp_templates[:3]:  # Limita a 3
                context_parts.append(f"- [{t['category']}] {t['name']} ({t['language']})")
            context_parts.append("")
        
        # 4. Intent detectada
        intent = intent_data.get('intent')
        if intent:
            context_parts.append(f"🔍 INTENÇÃO DETECTADA: {intent.value}")
            context_parts.append(f"Confiança: {intent_data.get('confidence', 0):.2f}")
            context_parts.append("")
        
        # 4. Dados da sessão
        if session_data:
            context_parts.append("📊 DADOS DO CLIENTE:")
            if session_data.get('has_cart'):
                context_parts.append(f"- Carrinho ativo: R$ {session_data['cart_total']:.2f} ({session_data['cart_items_count']} itens)")
            if session_data.get('has_order'):
                context_parts.append(f"- Pedido em andamento: {session_data['order_id']}")
            if session_data.get('pix_pending'):
                context_parts.append("- Pagamento PIX pendente")
            context_parts.append("")
        
        # 5. Instruções para o LLM
        context_parts.append("💡 INSTRUÇÕES:")
        context_parts.append("- Você é o assistente virtual principal")
        context_parts.append("- Use os templates de automação acima quando apropriado (adapte se necessário)")
        context_parts.append("- PREFIRA usar JASPER TEMPLATES quando quiser oferecer BOTÕES interativos")
        context_parts.append("- Os templates oficiais do WhatsApp são para envio via API (não use no texto)")
        context_parts.append("- Seja natural, amigável e prestativo")
        context_parts.append("- Se não souber algo, ofereça falar com um atendente humano")
        context_parts.append("")
        context_parts.append("🎯 QUANDO USAR CADA TIPO:")
        context_parts.append("- Saudação inicial → Jasper greeting (tem botões de cardápio/pedido)")
        context_parts.append("- Mostrar menu → Jasper menu_categories (tem botões de categorias)")
        context_parts.append("- Produto específico → Jasper product_card (tem botões de adicionar)")
        context_parts.append("- Ver carrinho → Jasper cart_summary (tem botões de finalizar)")
        context_parts.append("- Pedido confirmado → Jasper order_confirmation (tem botões de PIX)")
        context_parts.append("- Pagamento OK → Jasper payment_confirmed (tem botões de acompanhar)")
        context_parts.append("- Não entendeu → Jasper fallback (tem botões de ajuda)")
        
        return "\n".join(context_parts)
    
    def _get_jasper_template_for_response(self, response_text: str, intent: IntentType) -> Optional[Dict]:
        """
        Verifica se o LLM está tentando usar um Jasper Template.
        Retorna o template Jasper apropriado baseado na resposta ou intent.
        """
        response_lower = response_text.lower()
        jasper_templates = self._get_jasper_templates()
        
        # Mapeia intents para Jasper Templates
        intent_to_jasper = {
            IntentType.GREETING: 'greeting',
            IntentType.MENU_REQUEST: 'menu_categories',
            IntentType.PRODUCT_INQUIRY: 'product_card',
            IntentType.PRODUCT_MENTION: 'product_card',
            IntentType.ADD_TO_CART: 'product_card',
            IntentType.VIEW_CART: 'cart_summary',
            IntentType.CHECKOUT: 'cart_summary',
            IntentType.CREATE_ORDER: 'order_confirmation',
            IntentType.ORDER_STATUS: 'order_status',
            IntentType.PAYMENT_INFO: 'order_confirmation',
            IntentType.PAYMENT_STATUS: 'payment_confirmed',
            IntentType.BUSINESS_HOURS: 'need_help',
            IntentType.LOCATION: 'need_help',
            IntentType.HELP: 'need_help',
            IntentType.FALLBACK: 'fallback',
            IntentType.UNKNOWN: 'fallback',
        }
        
        # Primeiro tenta detectar pela intent
        if intent in intent_to_jasper:
            template_name = intent_to_jasper[intent]
            for t in jasper_templates:
                if t['name'] == template_name:
                    return t
        
        # Depois tenta detectar por palavras-chave na resposta
        keywords_map = {
            'greeting': ['bem-vindo', 'boas-vindas', 'olá', 'oi', 'como posso ajudar'],
            'menu_categories': ['cardápio', 'menu', 'categorias', 'opções'],
            'product_card': ['produto', 'item', 'adicionar'],
            'cart_summary': ['carrinho', 'resumo', 'finalizar'],
            'order_confirmation': ['pedido confirmado', 'pix', 'código pix'],
            'payment_confirmed': ['pagamento confirmado', 'pago', 'confirmado'],
            'need_help': ['ajuda', 'dúvida', 'suporte'],
            'fallback': ['não entendi', 'desculpe', 'não consegui'],
        }
        
        for template_name, keywords in keywords_map.items():
            if any(kw in response_lower for kw in keywords):
                for t in jasper_templates:
                    if t['name'] == template_name:
                        return t
        
        return None
    
    def _get_jasper_template_for_intent(self, intent: IntentType) -> Optional[Dict]:
        """
        Retorna o Jasper Template apropriado baseado na intent detectada.
        Isso garante que sempre teremos botões interativos para ações principais.
        """
        jasper_templates = self._get_jasper_templates()
        
        # Mapeamento completo de intents para templates
        intent_to_jasper = {
            IntentType.GREETING: 'greeting',
            IntentType.MENU_REQUEST: 'menu_categories',
            IntentType.PRODUCT_INQUIRY: 'product_card',
            IntentType.PRODUCT_MENTION: 'product_card',
            IntentType.ADD_TO_CART: 'product_card',
            IntentType.VIEW_CART: 'cart_summary',
            IntentType.CHECKOUT: 'cart_summary',
            IntentType.CREATE_ORDER: 'order_confirmation',
            IntentType.ORDER_STATUS: 'order_status',
            IntentType.PAYMENT_INFO: 'order_confirmation',
            IntentType.PAYMENT_STATUS: 'payment_confirmed',
            IntentType.BUSINESS_HOURS: 'need_help',
            IntentType.LOCATION: 'need_help',
            IntentType.HELP: 'need_help',
            IntentType.FALLBACK: 'fallback',
            IntentType.UNKNOWN: 'fallback',
        }
        
        template_name = intent_to_jasper.get(intent)
        if template_name:
            for t in jasper_templates:
                if t['name'] == template_name:
                    return t
        
        return None
    
    def _render_jasper_template(self, template: Dict, session_data: Dict) -> Dict:
        """Renderiza um Jasper Template com os dados REAIS da aplicação Pastita."""
        template_name = template['name']
        
        # Prepara variáveis básicas
        customer_name = self.conversation.contact_name or 'Cliente'
        company_name = self.company.company_name if self.company else 'Nossa Loja'
        
        # Obtém Store real da aplicação
        store = None
        if self.company and hasattr(self.company, 'store') and self.company.store_id:
            store = self.company.store
        
        # Renderiza o template apropriado com dados REAIS
        if template_name == 'greeting':
            jasper_template = JasperTemplates.greeting(customer_name, company_name)
            
        elif template_name == 'menu_categories':
            # Busca categorias REAIS do banco de dados
            if store:
                categories = list(store.categories.filter(
                    is_active=True
                ).order_by('sort_order')[:3].values_list('name', flat=True))
            else:
                categories = []
            
            # Fallback se não tiver categorias
            if not categories:
                categories = ['🍝 Massas', '🥗 Saladas', '🥤 Bebidas']
            
            jasper_template = JasperTemplates.menu_categories(company_name, categories)
            
        elif template_name == 'product_card':
            # Busca um produto real (destaque ou mais vendido)
            product_data = self._get_featured_product_data(store)
            jasper_template = JasperTemplates.product_card(product_data)
            
        elif template_name == 'cart_summary':
            # Busca itens REAIS do carrinho do CustomerSession ou StoreCart
            cart_items, cart_total = self._get_real_cart_data(session_data)
            jasper_template = JasperTemplates.cart_summary(cart_items, cart_total, customer_name)
            
        elif template_name == 'order_confirmation':
            # Busca dados REAIS do pedido
            order_data = self._get_real_order_data(session_data)
            jasper_template = JasperTemplates.order_confirmation(
                order_data['order_number'],
                order_data['total'],
                order_data['items'],
                order_data['pix_code'],
                order_data['pix_ticket_url']
            )
            
        elif template_name == 'payment_confirmed':
            # Busca dados reais do pedido para tempo estimado
            order_number = session_data.get('order_id', 'PED-001')
            # Tempo estimado baseado na configuração da loja ou padrão
            estimated_time = "40-50 min"
            if store and store.metadata:
                estimated_time = store.metadata.get('delivery_time', '40-50 min')
            jasper_template = JasperTemplates.payment_confirmed(order_number, estimated_time)
            
        elif template_name == 'order_status_update':
            # Busca status real do pedido
            order_status = self._get_order_status(session_data)
            jasper_template = JasperTemplates.order_status_update(
                session_data.get('order_id', 'PED-001'),
                order_status['status'],
                order_status['message']
            )
            
        elif template_name == 'business_hours':
            # Busca horário de funcionamento REAL da Store
            hours = self._get_store_operating_hours(store)
            jasper_template = JasperTemplates.business_hours(hours)
            
        elif template_name == 'need_help':
            jasper_template = JasperTemplates.need_help()
            
        elif template_name == 'fallback':
            jasper_template = JasperTemplates.fallback_message()
            
        else:
            # Default: greeting
            jasper_template = JasperTemplates.greeting(customer_name, company_name)
        
        # Renderiza com TemplateRenderer
        rendered = TemplateRenderer.render(
            jasper_template,
            customer_name=customer_name,
            company_name=company_name
        )
        
        return rendered
    
    def _get_featured_product_data(self, store) -> Dict:
        """Busca um produto em destaque do banco de dados."""
        from apps.stores.models import StoreProduct
        
        product = None
        if store:
            # Tenta buscar produto em destaque primeiro
            product = StoreProduct.objects.filter(
                store=store,
                status='active',
                featured=True
            ).first()
            
            # Se não encontrou, busca o mais vendido
            if not product:
                product = StoreProduct.objects.filter(
                    store=store,
                    status='active'
                ).order_by('-sold_count').first()
        
        if product:
            return {
                'id': str(product.id),
                'name': product.name,
                'price': float(product.price),
                'description': product.short_description or product.description[:100] if product.description else '',
            }
        
        # Fallback
        return {
            'id': 'default',
            'name': 'Produto em Destaque',
            'price': 35.00,
            'description': 'Conheça nossos produtos especiais!',
        }
    
    def _get_real_cart_data(self, session_data: Dict) -> tuple:
        """Busca dados REAIS do carrinho do CustomerSession ou StoreCart."""
        items = []
        total = session_data.get('cart_total', 0)
        
        # Tenta buscar do CustomerSession.cart_data primeiro
        if session_data.get('has_cart') and session_data.get('cart_data'):
            cart_data = session_data.get('cart_data', {})
            cart_items = cart_data.get('items', [])
            for item in cart_items:
                items.append({
                    'quantity': item.get('quantity', 1),
                    'name': item.get('name', 'Produto'),
                    'total': float(item.get('total', 0)) if item.get('total') else 0
                })
            total = float(cart_data.get('total', 0)) if cart_data.get('total') else total
        
        # Se não encontrou no session_data, tenta buscar StoreCart
        if not items and self.company and self.company.store_id:
            from apps.stores.models import StoreCart, StoreCartItem
            
            # Busca carrinho ativo pelo número de telefone
            carts = StoreCart.objects.filter(
                store=self.company.store,
                is_active=True
            ).order_by('-updated_at')[:1]
            
            for cart in carts:
                cart_items = StoreCartItem.objects.filter(cart=cart).select_related('product')
                for item in cart_items:
                    items.append({
                        'quantity': item.quantity,
                        'name': item.product.name if item.product else 'Produto',
                        'total': float(item.subtotal)
                    })
                total = float(cart.subtotal)
                break
        
        # Se ainda não encontrou, usa exemplo
        if not items:
            items = [{'quantity': 1, 'name': 'Carrinho vazio', 'total': 0}]
        
        return items, total
    
    def _get_real_order_data(self, session_data: Dict) -> Dict:
        """Busca dados REAIS do pedido do banco de dados."""
        order_number = session_data.get('order_id')
        
        if order_number and self.company and self.company.store_id:
            from apps.stores.models import StoreOrder, StoreOrderItem
            
            try:
                order = StoreOrder.objects.get(
                    store=self.company.store,
                    order_number=order_number
                )
                
                # Busca itens do pedido
                order_items = []
                for item in StoreOrderItem.objects.filter(order=order):
                    order_items.append({
                        'quantity': item.quantity,
                        'name': item.product_name
                    })
                
                return {
                    'order_number': order.order_number,
                    'total': float(order.total),
                    'items': order_items or [{'quantity': 1, 'name': 'Pedido'}],
                    'pix_code': order.pix_code or 'PIX123...',
                    'pix_ticket_url': order.pix_ticket_url or ''
                }
            except StoreOrder.DoesNotExist:
                pass
        
        # Fallback com dados da sessão ou padrão
        return {
            'order_number': order_number or 'PED-001',
            'total': session_data.get('cart_total', 0),
            'items': [{'quantity': 1, 'name': 'Pedido'}],
            'pix_code': session_data.get('pix_code', 'PIX123...'),
            'pix_ticket_url': ''
        }
    
    def _get_order_status(self, session_data: Dict) -> Dict:
        """Busca o status real do pedido."""
        order_number = session_data.get('order_id')
        
        if order_number and self.company and self.company.store_id:
            from apps.stores.models import StoreOrder
            
            try:
                order = StoreOrder.objects.get(
                    store=self.company.store,
                    order_number=order_number
                )
                
                status_messages = {
                    'confirmed': 'Seu pedido foi confirmado e já está sendo preparado!',
                    'preparing': 'Nossos chefs estão preparando seu pedido com carinho!',
                    'ready': 'Seu pedido está pronto para retirada ou saiu para entrega!',
                    'out_for_delivery': 'Seu pedido está a caminho! Nosso entregador logo chega.',
                    'delivered': 'Pedido entregue! Esperamos que aproveite sua refeição! 🎉',
                }
                
                return {
                    'status': order.status,
                    'message': status_messages.get(order.status, 'Seu pedido está em andamento.')
                }
            except StoreOrder.DoesNotExist:
                pass
        
        return {
            'status': 'processing',
            'message': 'Seu pedido está sendo processado.'
        }
    
    def _get_store_operating_hours(self, store) -> Dict:
        """Busca horário de funcionamento real da loja."""
        if not store or not store.operating_hours:
            return {
                'Segunda': '09:00 - 18:00',
                'Terça': '09:00 - 18:00',
                'Quarta': '09:00 - 18:00',
                'Quinta': '09:00 - 18:00',
                'Sexta': '09:00 - 18:00',
                'Sábado': '09:00 - 14:00',
                'Domingo': 'Fechado'
            }
        
        # Converte os dias do formato inglês para português
        day_map = {
            'monday': 'Segunda',
            'tuesday': 'Terça',
            'wednesday': 'Quarta',
            'thursday': 'Quinta',
            'friday': 'Sexta',
            'saturday': 'Sábado',
            'sunday': 'Domingo'
        }
        
        hours = {}
        for day_en, day_pt in day_map.items():
            day_data = store.operating_hours.get(day_en, {})
            if day_data.get('open') and day_data.get('close'):
                hours[day_pt] = f"{day_data['open']} - {day_data['close']}"
            else:
                hours[day_pt] = 'Fechado'
        
        return hours
    
    def _get_template_for_response(self, response_text: str) -> Optional[AutoMessage]:
        """
        Verifica se o LLM está tentando usar um template específico.
        Procura por referências a event_types na resposta.
        """
        if not self.company:
            return None
        
        # Mapeia possíveis referências a event_types
        event_type_keywords = {
            'welcome': ['bem-vindo', 'boas-vindas', 'olá', 'oi'],
            'menu': ['cardápio', 'menu', 'produtos', 'catálogo'],
            'business_hours': ['horário', 'funcionamento', 'aberto'],
            'cart_created': ['carrinho', 'adicionado'],
            'order_received': ['pedido recebido', 'confirmado'],
            'payment_confirmed': ['pagamento confirmado', 'pago'],
        }
        
        response_lower = response_text.lower()
        
        for event_type, keywords in event_type_keywords.items():
            if any(kw in response_lower for kw in keywords):
                template = AutoMessage.objects.filter(
                    company=self.company,
                    event_type=event_type,
                    is_active=True
                ).first()
                if template:
                    return template
        
        return None
    
    def _try_handler_as_tool(self, intent: IntentType, intent_data: Dict) -> Optional[HandlerResult]:
        """
        Executa um handler como ferramenta que o LLM pode usar.
        Retorna o resultado para o LLM incorporar na resposta.
        """
        handler = get_handler(intent, self.account, self.conversation)
        
        if not handler:
            return None
        
        try:
            result = handler.handle(intent_data)
            return result
        except Exception as e:
            logger.error(f"[LLMOrchestrator] Handler error: {e}")
            return None
    
    def process_message(self, message_text: str) -> UnifiedResponse:
        """
        Processa mensagem com LLM como orquestrador.
        
        Fluxo:
        1. Detecta intent
        2. Coleta contexto (templates, sessão)
        3. Chama LLM com contexto completo
        4. LLM decide como responder
        5. Retorna resposta
        """
        start_time = time.time()
        
        if not message_text or not message_text.strip():
            return UnifiedResponse(
                content="Desculpe, não recebi sua mensagem. Pode tentar novamente?",
                source=ResponseSource.FALLBACK
            )
        
        clean_message = message_text.strip()
        
        # 1. Detectar intent (para contexto)
        intent_data = self.detector.detect(clean_message.lower())
        intent = intent_data['intent']
        
        if self.debug:
            logger.info(f"[LLMOrchestrator] Intent: {intent.value}")
        
        # 2. Coletar dados de contexto
        templates = self._get_available_templates()
        session_data = self._get_session_data()
        
        # 3. Construir contexto para LLM
        context = self._build_llm_context(clean_message, intent_data, templates, session_data)
        
        # 4. Chamar LLM
        agent = self._get_active_agent()
        
        if not agent:
            logger.error("[LLMOrchestrator] No agent configured")
            return self._fallback_response()
        
        try:
            service = LangchainService(agent)
            
            # Busca session_id existente
            from apps.agents.models import AgentConversation
            agent_conv = AgentConversation.objects.filter(
                agent=agent,
                phone_number=self.conversation.phone_number
            ).order_by('-last_message_at').first()
            
            session_id = str(agent_conv.session_id) if agent_conv else None
            
            # Prepara mensagem com contexto
            enriched_message = f"{context}\n\n---\n\nMENSAGEM DO CLIENTE: {clean_message}"
            
            if self.debug:
                logger.info(f"[LLMOrchestrator] Sending to LLM with context ({len(enriched_message)} chars)")
            
            result = service.process_message(
                message=enriched_message,
                session_id=session_id,
                phone_number=self.conversation.phone_number,
                conversation_id=str(self.conversation.id)
            )
            
            response_text = result.get('response', '')
            
            # 5. SEMPRE tenta usar Jasper Template baseado na intent primeiro
            # Isso garante que teremos botões interativos para as ações principais
            jasper_template = self._get_jasper_template_for_intent(intent)
            if not jasper_template:
                # Fallback: tenta detectar pela resposta do LLM
                jasper_template = self._get_jasper_template_for_response(response_text, intent)
            
            if jasper_template:
                # Renderiza Jasper Template com contexto
                rendered = self._render_jasper_template(jasper_template, session_data)
                
                self.stats['agent_template'] += 1
                
                self._log_intent(
                    intent_data=intent_data,
                    source='jasper_template',
                    response_text=rendered['body'],
                    start_time=start_time,
                    metadata={
                        'jasper_template': jasper_template['name'],
                        'has_buttons': True,
                        'model': result.get('model'),
                    }
                )
                
                # Processa botões - podem ser strings ou objetos {id, title}
                processed_buttons = []
                for i, btn in enumerate(rendered.get('buttons', [])):
                    if isinstance(btn, dict):
                        # Já é um objeto com id/title
                        processed_buttons.append({
                            'id': btn.get('id', f"btn_{i}"),
                            'title': btn.get('title', str(btn))
                        })
                    else:
                        # É uma string
                        processed_buttons.append({'id': f"btn_{i}", 'title': str(btn)})
                
                return UnifiedResponse(
                    content=rendered['body'],
                    source=ResponseSource.AGENT_TEMPLATE,
                    buttons=processed_buttons,
                    interactive_type='buttons',
                    metadata={
                        'jasper_template': jasper_template['name'],
                        'header': rendered.get('header'),
                        'footer': rendered.get('footer'),
                        'model': result.get('model'),
                    }
                )
            
            # 6. Verifica se deve usar algum template de automação
            template = self._get_template_for_response(response_text)
            if template:
                # Renderiza template com contexto
                template_context = self._build_template_render_context(session_data)
                rendered = template.render_message(template_context)
                
                self.stats['agent_template'] += 1
                
                self._log_intent(
                    intent_data=intent_data,
                    source='agent_template',
                    response_text=rendered,
                    start_time=start_time,
                    metadata={
                        'template_id': str(template.id),
                        'template_event': template.event_type,
                        'llm_original': response_text[:200],
                    }
                )
                
                return UnifiedResponse(
                    content=rendered,
                    source=ResponseSource.AGENT_TEMPLATE,
                    buttons=template.buttons,
                    metadata={
                        'template_id': str(template.id),
                        'template_event': template.event_type,
                        'model': result.get('model'),
                    }
                )
            
            # 7. Verifica se deve usar handler
            handler_result = self._try_handler_as_tool(intent, intent_data)
            if handler_result and handler_result.response_text:
                # LLM pode incorporar o resultado do handler
                self.stats['agent_handler'] += 1
                
                self._log_intent(
                    intent_data=intent_data,
                    source='agent_handler',
                    response_text=handler_result.response_text,
                    start_time=start_time,
                    metadata={
                        'handler': handler_result.__class__.__name__ if hasattr(handler_result, '__class__') else 'unknown',
                        'llm_response': response_text[:200],
                    }
                )
                
                # Se handler tem resposta interativa, usa ela
                if handler_result.use_interactive:
                    return UnifiedResponse(
                        content=handler_result.response_text,
                        source=ResponseSource.AGENT_HANDLER,
                        buttons=handler_result.interactive_data.get('buttons') if handler_result.interactive_data else None,
                        interactive_type=handler_result.interactive_type,
                        metadata={'handler_used': True}
                    )
            
            # 8. Resposta direta do LLM
            self.stats['agent_direct'] += 1
            
            self._log_intent(
                intent_data=intent_data,
                source='agent_direct',
                response_text=response_text,
                start_time=start_time,
                metadata={
                    'model': result.get('model'),
                    'tokens_used': result.get('tokens_used'),
                }
            )
            
            return UnifiedResponse(
                content=response_text,
                source=ResponseSource.AGENT_DIRECT,
                metadata={
                    'model': result.get('model'),
                    'tokens_used': result.get('tokens_used'),
                    'processing_time': result.get('processing_time'),
                }
            )
            
        except Exception as e:
            logger.error(f"[LLMOrchestrator] Error: {e}", exc_info=True)
            return self._fallback_response()
    
    def _build_template_render_context(self, session_data: Dict) -> Dict[str, str]:
        """Constrói contexto para renderizar templates."""
        context = {
            'phone_number': self.conversation.phone_number,
            'customer_name': self.conversation.contact_name or 'Cliente',
            'company_name': self.company.company_name if self.company else 'Nossa Empresa',
            'cart_total': f"R$ {session_data.get('cart_total', 0):.2f}" if session_data.get('cart_total') else '',
            'cart_item_count': str(session_data.get('cart_items_count', 0)),
            'order_number': session_data.get('order_id', ''),
        }
        return context
    
    def _fallback_response(self) -> UnifiedResponse:
        """Resposta de fallback quando algo dá errado."""
        self.stats['fallbacks'] += 1
        return UnifiedResponse(
            content="Desculpe, estou com dificuldades no momento. Um atendente humano pode te ajudar?",
            source=ResponseSource.FALLBACK
        )
    
    def _log_intent(
        self,
        intent_data: Dict,
        source: str,
        response_text: str,
        start_time: float,
        metadata: Optional[Dict] = None
    ):
        """Registra log da interação."""
        try:
            if not self.company:
                return
            
            processing_time = int((time.time() - start_time) * 1000)
            
            IntentLog.objects.create(
                company=self.company,
                conversation=self.conversation,
                phone_number=self.conversation.phone_number,
                message_text=intent_data.get('original_message', '')[:500],
                intent_type=intent_data['intent'].value,
                method='llm',  # Usa 'llm' para indicar que foi processado pelo LLM orquestrador
                confidence=float(intent_data.get('confidence', 0)),
                handler_used=source,
                response_text=response_text[:1000] if response_text else "",
                response_type='text',
                processing_time_ms=processing_time,
                entities=intent_data.get('entities', {}),
                metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"[LLMOrchestrator] Error logging: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do serviço."""
        return {
            **self.stats,
            'llm_active': True,
            'agent_configured': self._get_active_agent() is not None,
        }


# Função utilitária
process_message_unified = LLMOrchestratorService
