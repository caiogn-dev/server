"""
WhatsApp Intent Handlers

Handlers específicos para cada tipo de intenção detectada.
Cada handler retorna uma resposta adequada ou None para fallback.
"""
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
import logging

from apps.whatsapp.intents.detector import IntentType, IntentData
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
from apps.automation.models import AutoMessage
from apps.stores.models import StoreProduct
from apps.stores.models.order import StoreOrder as Order

logger = logging.getLogger(__name__)


class HandlerResult:
    """Resultado do processamento de um handler"""
    
    def __init__(
        self,
        response_text: Optional[str] = None,
        use_interactive: bool = False,
        interactive_type: Optional[str] = None,  # 'buttons', 'list'
        interactive_data: Optional[Dict] = None,
        requires_llm: bool = False
    ):
        self.response_text = response_text
        self.use_interactive = use_interactive
        self.interactive_type = interactive_type
        self.interactive_data = interactive_data or {}
        self.requires_llm = requires_llm
    
    @classmethod
    def text(cls, text: str) -> 'HandlerResult':
        """Cria resultado com texto simples"""
        return cls(response_text=text)
    
    @classmethod
    def buttons(cls, body: str, buttons: list) -> 'HandlerResult':
        """Cria resultado com botões interativos"""
        return cls(
            response_text="BUTTONS_SENT",
            use_interactive=True,
            interactive_type='buttons',
            interactive_data={'body': body, 'buttons': buttons}
        )
    
    @classmethod
    def list_message(cls, body: str, button: str, sections: list) -> 'HandlerResult':
        """Cria resultado com lista interativa"""
        return cls(
            response_text="LIST_SENT",
            use_interactive=True,
            interactive_type='list',
            interactive_data={'body': body, 'button': button, 'sections': sections}
        )
    
    @classmethod
    def needs_llm(cls) -> 'HandlerResult':
        """Indica que precisa de LLM"""
        return cls(requires_llm=True)
    
    @classmethod
    def none(cls) -> 'HandlerResult':
        """Sem resposta automática"""
        return cls()


class IntentHandler:
    """Handler base para intenções"""
    
    def __init__(self, account, conversation, company_profile=None):
        self.account = account
        self.conversation = conversation
        self.company_profile = company_profile or getattr(account, 'company_profile', None)
        self.whatsapp_service = WhatsAppAPIService(account)
        self.store = self._get_store()
    
    def _get_store(self):
        """Retorna a loja associada"""
        if self.company_profile and hasattr(self.company_profile, 'store'):
            return self.company_profile.store
        return None
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        """Processa a intenção e retorna resultado"""
        raise NotImplementedError
    
    def get_customer_name(self) -> str:
        """Retorna nome do cliente"""
        return self.conversation.contact_name or 'Cliente'


class GreetingHandler(IntentHandler):
    """Handler para saudações"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Handling greeting for {self.get_customer_name()}")
        
        # Busca mensagem de welcome configurada
        try:
            welcome_msg = AutoMessage.objects.filter(
                company=self.company_profile,
                event_type=AutoMessage.EventType.WELCOME,
                is_active=True
            ).first()
            
            if welcome_msg:
                text = welcome_msg.render({
                    'customer_name': self.get_customer_name(),
                    'store_name': self.company_profile.company_name if self.company_profile else 'Nossa Loja',
                })
                return HandlerResult.text(text)
            
        except Exception as e:
            logger.error(f"Error loading welcome message: {e}")
        
        # Fallback padrão
        store_name = self.company_profile.company_name if self.company_profile else 'Pastita'
        
        text = (
            f"👋 Olá, {self.get_customer_name()}!\n\n"
            f"Bem-vindo à *{store_name}*!\n\n"
            f"Como posso ajudar você hoje?"
        )
        
        # Envia botões de ações principais
        return HandlerResult.buttons(
            body=text,
            buttons=[
                {'id': 'menu_catalog', 'title': '📋 Cardápio'},
                {'id': 'menu_order', 'title': '🛒 Fazer Pedido'},
                {'id': 'menu_help', 'title': '❓ Ajuda'},
            ]
        )


class PriceCheckHandler(IntentHandler):
    """Handler para consulta de preços"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        entities = intent_data.get('entities', {})
        product_name = entities.get('product_name')
        
        logger.info(f"Price check for: {product_name}")
        
        if not self.store:
            return HandlerResult.text("Desculpe, não encontrei informações da loja no momento. 😔")
        
        # Se mencionou produto específico
        if product_name:
            products = StoreProduct.objects.filter(
                store=self.store,
                name__icontains=product_name,
                is_active=True
            )[:5]
            
            if products:
                if len(products) == 1:
                    # Produto único - mostra detalhes
                    p = products[0]
                    response = (
                        f"💰 *{p.name}*\n"
                        f"Preço: *R$ {p.price}*\n\n"
                    )
                    if p.description:
                        response += f"{p.description}\n\n"
                    
                    # Botão para adicionar ao carrinho
                    return HandlerResult.buttons(
                        body=response,
                        buttons=[
                            {'id': f'add_{p.id}_1', 'title': '🛒 Adicionar'},
                            {'id': f'details_{p.id}', 'title': 'ℹ️ Detalhes'},
                            {'id': 'view_catalog', 'title': '📋 Ver mais'},
                        ]
                    )
                else:
                    # Múltiplos produtos - lista
                    response = f"💰 Encontrei esses produtos:\n\n"
                    for p in products:
                        response += f"• *{p.name}*: R$ {p.price}\n"
                    
                    response += "\nQual você quer?"
                    return HandlerResult.text(response)
            else:
                return HandlerResult.text(
                    f"Não encontrei '{product_name}'. 😕\n\n"
                    f"Quer ver nosso cardápio completo?"
                )
        
        # Retorna produtos populares
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        ).order_by('-created_at')[:5]
        
        if products:
            response = f"💰 *Alguns dos nossos produtos:*\n\n"
            for p in products:
                response += f"• {p.name}: R$ {p.price}\n"
            
            response += f"\nQuer ver mais opções ou detalhes de algum?"
            return HandlerResult.text(response)
        
        return HandlerResult.text(
            "Nosso cardápio está sendo atualizado! 🔄\n"
            "Tente novamente em alguns minutos."
        )


class MenuRequestHandler(IntentHandler):
    """Handler para solicitação de cardápio"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Menu request for store: {self.store}")
        
        if not self.store:
            return HandlerResult.text("Cardápio não disponível no momento. 😔")
        
        # Busca categorias com produtos
        categories = StoreProduct.objects.filter(
            store=self.store,
            is_active=True,
            category__isnull=False
        ).values_list('category__name', flat=True).distinct()
        
        if not categories:
            # Sem categorias - mostra todos os produtos
            products = StoreProduct.objects.filter(
                store=self.store,
                is_active=True
            )[:10]
            
            if products:
                sections = [{
                    'title': 'Todos os Produtos',
                    'rows': [
                        {
                            'id': f'product_{p.id}',
                            'title': p.name[:24],
                            'description': f'R$ {p.price}'
                        }
                        for p in products
                    ]
                }]
            else:
                return HandlerResult.text("Nenhum produto disponível no momento. 😔")
        else:
            # Com categorias
            sections = []
            for cat in categories[:5]:
                products = StoreProduct.objects.filter(
                    store=self.store,
                    category__name=cat,
                    is_active=True
                )[:5]
                
                if products:
                    section = {
                        'title': cat[:24],
                        'rows': [
                            {
                                'id': f'product_{p.id}',
                                'title': p.name[:24],
                                'description': f'R$ {p.price} - {p.description[:20] if p.description else ""}'
                            }
                            for p in products
                        ]
                    }
                    sections.append(section)
        
        # Envia lista interativa
        return HandlerResult.list_message(
            body=f"📋 *Cardápio - {self.store.name}*\n\nEscolha uma opção:",
            button="Ver opções",
            sections=sections
        )


class BusinessHoursHandler(IntentHandler):
    """Handler para horário de funcionamento"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )
        
        from datetime import datetime
        
        # Pega horário de hoje
        today = datetime.now().strftime('%A').lower()
        
        # Mapeia dias da semana
        day_names = {
            'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
            'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado', 'sunday': 'Domingo'
        }
        
        # Tenta pegar horário do banco
        try:
            hours = self.store.operating_hours or {}
            today_hours = hours.get(today, {})
            
            if today_hours:
                open_time = today_hours.get('open', '10:00')
                close_time = today_hours.get('close', '20:00')
                
                response = (
                    f"🕐 *Horário de hoje ({day_names.get(today, 'Hoje')}):*\n"
                    f"{open_time} às {close_time}\n\n"
                )
            else:
                response = "🕐 *Horário de hoje:* Fechado\n\n"
            
            # Adiciona horário completo
            response += "*Horário da semana:*\n"
            for day_code, day_name in day_names.items():
                day_hours = hours.get(day_code, {})
                if day_hours:
                    response += f"{day_name}: {day_hours.get('open', '--:--')} às {day_hours.get('close', '--:--')}\n"
                else:
                    response += f"{day_name}: Fechado\n"
            
            return HandlerResult.text(response)
            
        except Exception as e:
            logger.error(f"Error getting business hours: {e}")
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )


class DeliveryInfoHandler(IntentHandler):
    """Handler para informações de entrega"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🚚 *Informações de Entrega*\n\n"
                "• Tempo médio: 40-60 minutos\n"
                "• Taxa de entrega: a consultar\n"
                "• Área de cobertura: Consulte seu CEP\n\n"
                "Quer fazer um pedido?"
            )
        
        try:
            delivery_settings = self.store.delivery_settings or {}
            
            response = f"🚚 *{self.store.name} - Entrega*\n\n"
            
            # Tempo de entrega
            delivery_time = delivery_settings.get('delivery_time', '40-60')
            response += f"⏱️ Tempo médio: *{delivery_time} minutos*\n"
            
            # Taxa de entrega
            delivery_fee = delivery_settings.get('delivery_fee')
            if delivery_fee:
                response += f"💰 Taxa de entrega: *R$ {delivery_fee}*\n"
            else:
                response += f"💰 Taxa de entrega: *Consultar*\n"
            
            # Pedido mínimo
            min_order = delivery_settings.get('min_order')
            if min_order:
                response += f"📦 Pedido mínimo: *R$ {min_order}*\n"
            
            response += "\nQuer fazer um pedido?"
            
            return HandlerResult.buttons(
                body=response,
                buttons=[
                    {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
                    {'id': 'check_cep', 'title': '📍 Consultar CEP'},
                    {'id': 'view_menu', 'title': '📋 Cardápio'},
                ]
            )
            
        except Exception as e:
            logger.error(f"Error getting delivery info: {e}")
            return HandlerResult.text(
                "🚚 *Informações de Entrega*\n\n"
                "• Tempo médio: 40-60 minutos\n"
                "• Taxa de entrega: a consultar\n\n"
                "Quer fazer um pedido?"
            )


class TrackOrderHandler(IntentHandler):
    """Handler para rastrear pedido"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        entities = intent_data.get('entities', {})
        order_number = entities.get('order_number')
        
        logger.info(f"Track order: number={order_number}")
        
        # Se não informou número, busca último pedido
        if not order_number:
            last_order = Order.objects.filter(
                customer_phone=self.conversation.phone_number,
                store=self.store
            ).order_by('-created_at').first()
        else:
            last_order = Order.objects.filter(
                order_number=order_number,
                customer_phone=self.conversation.phone_number
            ).first()
        
        if last_order:
            status_map = {
                'pending': '⏳ Aguardando confirmação',
                'confirmed': '✅ Pedido confirmado',
                'preparing': '👨‍🍳 Em preparo',
                'ready': '✨ Pronto para retirada',
                'out_for_delivery': '🛵 Saiu para entrega',
                'delivered': '📦 Entregue',
                'cancelled': '❌ Cancelado',
            }
            
            status_display = status_map.get(last_order.status, f'Status: {last_order.status}')
            
            response = (
                f"📦 *Pedido #{last_order.order_number}*\n"
                f"{status_display}\n"
                f"Data: {last_order.created_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Total: R$ {last_order.total}"
            )
            
            # Se ainda está em andamento, mostra botão de acompanhamento
            if last_order.status in ['pending', 'confirmed', 'preparing', 'out_for_delivery']:
                return HandlerResult.buttons(
                    body=response,
                    buttons=[
                        {'id': f'track_{last_order.id}', 'title': '🔄 Atualizar'},
                        {'id': 'contact_support', 'title': '📞 Suporte'},
                    ]
                )
            
            return HandlerResult.text(response)
        
        return HandlerResult.text(
            "Não encontrei pedidos recentes. 😕\n\n"
            "Quer fazer um pedido novo?"
        )


class CreateOrderHandler(IntentHandler):
    """Handler para iniciar pedido"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Create order intent")
        
        # Inicia fluxo de pedido com botões
        return HandlerResult.buttons(
            body=(
                f"🛒 *Vamos fazer seu pedido, {self.get_customer_name()}!*\n\n"
                f"Como prefere começar?"
            ),
            buttons=[
                {'id': 'order_catalog', 'title': '📋 Ver Cardápio'},
                {'id': 'order_quick', 'title': '⚡ Pedido Rápido'},
                {'id': 'order_help', 'title': '❓ Preciso de Ajuda'},
            ]
        )


class PaymentStatusHandler(IntentHandler):
    """Handler para status de pagamento"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        # Busca último pedido pendente
        pending_order = Order.objects.filter(
            customer_phone=self.conversation.phone_number,
            store=self.store,
            status='pending_payment'
        ).order_by('-created_at').first()
        
        if pending_order and pending_order.pix_code:
            return HandlerResult.buttons(
                body=(
                    f"💳 *Pagamento Pendente*\n\n"
                    f"Pedido: #{pending_order.order_number}\n"
                    f"Valor: R$ {pending_order.total}\n\n"
                    f"Copie o código PIX abaixo 👇"
                ),
                buttons=[
                    {'id': f'pix_copy_{pending_order.id}', 'title': '📋 Copiar PIX'},
                    {'id': 'send_comprovante', 'title': '📤 Enviar Comprovante'},
                    {'id': 'cancel_order', 'title': '❌ Cancelar'},
                ]
            )
        
        return HandlerResult.text(
            "Não encontrei pagamentos pendentes. ✅\n\n"
            "Quer fazer um pedido novo?"
        )


class LocationHandler(IntentHandler):
    """Handler para localização/endereço"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if self.store and self.store.address:
            return HandlerResult.text(
                f"📍 *Endereço*\n\n"
                f"{self.store.name}\n"
                f"{self.store.address}\n\n"
                f"Aguardamos sua visita! 😊"
            )
        
        return HandlerResult.text(
            "📍 Entregamos em toda a região!\n\n"
            "Para fazer um pedido com entrega, é só me informar seu endereço completo."
        )


class ContactHandler(IntentHandler):
    """Handler para contato"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if self.store and self.store.phone:
            return HandlerResult.text(
                f"📞 *Contato*\n\n"
                f"WhatsApp: {self.store.phone}\n\n"
                f"Estamos aqui para ajudar! 😊"
            )
        
        return HandlerResult.text(
            "📞 *Atendimento*\n\n"
            "Estou aqui para ajudar!\n"
            "Se precisar falar com um atendente humano, digite 'atendente'."
        )


class HumanHandoffHandler(IntentHandler):
    """Handler para transferência para humano"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Human handoff requested by {self.get_customer_name()}")
        
        # Marca conversa para atendimento humano
        self.conversation.metadata['human_handoff'] = True
        self.conversation.metadata['handoff_requested_at'] = datetime.now().isoformat()
        self.conversation.save()
        
        return HandlerResult.text(
            f"👨‍💼 *Transferindo para atendimento humano...*\n\n"
            f"Um de nossos atendentes vai te atender em breve.\n"
            f"Por favor, aguarde um momento. 🙏"
        )


class FAQHandler(IntentHandler):
    """Handler para perguntas frequentes"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        # Retorna FAQ com botões
        return HandlerResult.buttons(
            body="❓ *Perguntas Frequentes*\n\nO que você quer saber?",
            buttons=[
                {'id': 'faq_hours', 'title': '🕐 Horário'},
                {'id': 'faq_delivery', 'title': '🚚 Entrega'},
                {'id': 'faq_payment', 'title': '💳 Pagamento'},
            ]
        )


class UnknownHandler(IntentHandler):
    """Handler para intenções desconhecidas"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Unknown intent, forwarding to LLM")
        return HandlerResult.needs_llm()


# ===== MAPEAMENTO DE HANDLERS =====
HANDLER_MAP = {
    IntentType.GREETING: GreetingHandler,
    IntentType.PRICE_CHECK: PriceCheckHandler,
    IntentType.MENU_REQUEST: MenuRequestHandler,
    IntentType.BUSINESS_HOURS: BusinessHoursHandler,
    IntentType.DELIVERY_INFO: DeliveryInfoHandler,
    IntentType.TRACK_ORDER: TrackOrderHandler,
    IntentType.PAYMENT_STATUS: PaymentStatusHandler,
    IntentType.LOCATION: LocationHandler,
    IntentType.CONTACT: ContactHandler,
    IntentType.CREATE_ORDER: CreateOrderHandler,
    IntentType.HUMAN_HANDOFF: HumanHandoffHandler,
    IntentType.FAQ: FAQHandler,
    IntentType.UNKNOWN: UnknownHandler,
    # Adicione mais conforme necessário
}


def get_handler(intent_type: IntentType, account, conversation) -> Optional[IntentHandler]:
    """Retorna o handler apropriado para a intenção"""
    handler_class = HANDLER_MAP.get(intent_type)
    if handler_class:
        return handler_class(account, conversation)
    return None
