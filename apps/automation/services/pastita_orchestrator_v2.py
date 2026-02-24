"""
Pastita Orchestrator - Versão Completa com LangGraph
Fluxo: greeting → menu → cart → delivery_method → address (if delivery) → payment_method → checkout → PIX
"""
import logging
import re
import json
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Tipos de intenção do usuário."""
    GREETING = "greeting"
    MENU_REQUEST = "menu_request"
    PRODUCT_INQUIRY = "product_inquiry"
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    VIEW_CART = "view_cart"
    CLEAR_CART = "clear_cart"
    CREATE_ORDER = "create_order"
    CONFIRM_ORDER = "confirm_order"
    CANCEL_ORDER = "cancel_order"
    
    # Novos intents para fluxo completo
    DELIVERY_METHOD = "delivery_method"
    DELIVERY_ADDRESS = "delivery_address"
    PAYMENT_METHOD = "payment_method"
    
    REQUEST_PIX = "request_pix"
    CONFIRM_PAYMENT = "confirm_payment"
    ORDER_STATUS = "order_status"
    BUSINESS_HOURS = "business_hours"
    DELIVERY_INFO = "delivery_info"
    HUMAN_HANDOFF = "human_handoff"
    UNKNOWN = "unknown"


class ResponseSource(Enum):
    """Origem da resposta."""
    TEMPLATE = "template"
    HANDLER = "handler"
    FALLBACK = "fallback"


@dataclass
class OrchestratorResponse:
    """Resposta padronizada."""
    content: str
    source: ResponseSource
    intent: IntentType
    buttons: Optional[List[Dict[str, str]]] = None
    metadata: Dict = field(default_factory=dict)


# =============================================================================
# HERE API INTEGRATION
# =============================================================================

class HereApiService:
    """Serviço de integração com HERE API para geocoding e routing."""
    
    def __init__(self):
        self.api_key = getattr(settings, 'HERE_API_KEY', '')
        self.base_url = "https://router.hereapi.com/v8"
        self.geocode_url = "https://geocode.search.hereapi.com/v1"
    
    def geocode_address(self, address: str) -> Optional[Dict]:
        """Converte endereço em coordenadas."""
        if not self.api_key:
            logger.warning("HERE_API_KEY não configurada")
            return None
        
        try:
            import requests
            
            url = f"{self.geocode_url}/geocode"
            params = {
                'q': address,
                'apiKey': self.api_key,
                'limit': 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('items'):
                item = data['items'][0]
                return {
                    'address': item.get('address', {}).get('label'),
                    'lat': item.get('position', {}).get('lat'),
                    'lng': item.get('position', {}).get('lng'),
                }
            return None
            
        except Exception as e:
            logger.error(f"Erro ao geocodificar endereço: {e}")
            return None
    
    def calculate_route(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Optional[Dict]:
        """Calcula distância e tempo entre dois pontos."""
        if not self.api_key:
            return None
        
        try:
            import requests
            
            url = f"{self.base_url}/routes"
            params = {
                'transportMode': 'car',
                'origin': f"{origin[0]},{origin[1]}",
                'destination': f"{destination[0]},{destination[1]}",
                'return': 'summary',
                'apiKey': self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('routes'):
                route = data['routes'][0]
                section = route.get('sections', [{}])[0]
                summary = section.get('summary', {})
                
                return {
                    'distance_m': summary.get('length', 0),
                    'distance_km': round(summary.get('length', 0) / 1000, 2),
                    'duration_min': round(summary.get('duration', 0) / 60, 0),
                }
            return None
            
        except Exception as e:
            logger.error(f"Erro ao calcular rota: {e}")
            return None
    
    def calculate_delivery_fee(self, distance_km: float) -> Decimal:
        """Calcula taxa de entrega baseada na distância."""
        base_fee = Decimal('5.00')
        
        if distance_km <= 3:
            return base_fee
        
        additional_km = distance_km - 3
        additional_fee = Decimal(str(additional_km)) * Decimal('1.50')
        
        return base_fee + additional_fee


# =============================================================================
# INTENT DETECTOR
# =============================================================================

class IntentDetector:
    """Detector de intenções usando regex."""
    
    PATTERNS = {
        IntentType.GREETING: [
            r'^(oi|ol[áa]|ola|eae|eai|bom dia|boa tarde|boa noite|salve|hey|hi|hello|opa|tudo bem|como vai)',
        ],
        IntentType.MENU_REQUEST: [
            r'(card[áa]pio|menu|o que (tem|voc[êe]s t[êe]m)|op[çc][õo]es|produtos|ver produtos)',
        ],
        IntentType.ADD_TO_CART: [
            r'(quero|vou querer|adiciona|coloca|me v[êe]|pedir|gostaria de)',
            r'(\d+\s+(rondelli|lasanha|nhoque|talharim|fettuccine|molho))',
        ],
        IntentType.VIEW_CART: [
            r'(carrinho|ver pedido|o que tem no carrinho|meu pedido|ver carrinho)',
        ],
        IntentType.CLEAR_CART: [
            r'(limpa carrinho|esvazia|tira tudo|cancela tudo|limpar)',
        ],
        IntentType.CREATE_ORDER: [
            r'(finalizar|fechar pedido|confirmar|quero pagar|fazer pedido|terminar)',
        ],
        IntentType.CANCEL_ORDER: [
            r'(cancela|n[ãa]o quero mais|desistir|cancelar)',
        ],
        IntentType.REQUEST_PIX: [
            r'(pix|gerar pix|c[óo]digo|qr code)',
        ],
        IntentType.CONFIRM_PAYMENT: [
            r'(paguei|j[áa] paguei|comprovante|enviei|transferi|pago)',
        ],
        IntentType.HUMAN_HANDOFF: [
            r'(atendente|humano|falar com pessoa|n[ãa]o entendi|n[ãa]o consegui)',
        ],
    }
    
    @classmethod
    def detect(cls, message: str) -> Tuple[IntentType, Dict[str, Any]]:
        """Detecta intenção da mensagem."""
        message_lower = message.lower().strip()
        
        for intent, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    return intent, {"confidence": 1.0, "method": "regex"}
        
        if re.match(r'^\d+$', message_lower):
            return IntentType.ADD_TO_CART, {"confidence": 0.8, "method": "regex", "quantity": int(message_lower)}
        
        return IntentType.UNKNOWN, {"confidence": 0.0, "method": "none"}


# =============================================================================
# PASTITA ORCHESTRATOR
# =============================================================================

class PastitaOrchestrator:
    """Orquestrador principal do bot Pastita com fluxo completo."""
    
    def __init__(self, conversation=None, store=None):
        self.conversation = conversation
        self.store = store
        self.here_api = HereApiService()
    
    def process_message(self, message: str, context: Optional[Dict] = None) -> OrchestratorResponse:
        """Processa mensagem do usuário."""
        try:
            intent, intent_data = IntentDetector.detect(message)
            logger.info(f"[Orchestrator] Intent: {intent.value}")
            
            session = self._get_or_create_session()
            handler = self._get_handler(intent, session, message)
            
            if handler:
                response = handler(message, intent_data, session)
                return response
            
            return self._fallback_response(message)
            
        except Exception as e:
            logger.exception(f"[Orchestrator] Error: {e}")
            return OrchestratorResponse(
                content="❌ Ocorreu um erro. Por favor, tente novamente ou digite *atendente*.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.UNKNOWN
            )
    
    def _get_or_create_session(self):
        """Obtém ou cria sessão do cliente."""
        from apps.automation.models import CustomerSession, CompanyProfile
        
        company = CompanyProfile.objects.filter(is_active=True).first()
        
        session, created = CustomerSession.objects.get_or_create(
            phone_number=self.conversation.phone_number,
            company=company,
            defaults={
                'session_id': f"session_{self.conversation.phone_number}_{datetime.now().timestamp()}",
                'cart_data': {'items': []},
                'cart_total': Decimal('0'),
                'status': 'active'
            }
        )
        return session
    
    def _get_handler(self, intent: IntentType, session, message: str):
        """Determina qual handler usar baseado no estado."""
        # Verifica estado da sessão primeiro (mais específico)
        if session.status == 'awaiting_delivery_method':
            return self._handle_delivery_method_selection
        elif session.status == 'awaiting_address':
            return self._handle_address_input
        elif session.status == 'awaiting_payment_method':
            return self._handle_payment_method_selection
        
        # Handlers por intenção
        handlers = {
            IntentType.GREETING: self._handle_greeting,
            IntentType.MENU_REQUEST: self._handle_menu,
            IntentType.ADD_TO_CART: self._handle_add_to_cart,
            IntentType.VIEW_CART: self._handle_view_cart,
            IntentType.CLEAR_CART: self._handle_clear_cart,
            IntentType.CREATE_ORDER: self._handle_create_order,
            IntentType.REQUEST_PIX: self._handle_request_pix,
            IntentType.CONFIRM_PAYMENT: self._handle_confirm_payment,
            IntentType.CANCEL_ORDER: self._handle_cancel_order,
            IntentType.HUMAN_HANDOFF: self._handle_human_handoff,
        }
        
        return handlers.get(intent)
    
    def _get_store_location(self) -> Dict:
        """Obtém localização da loja."""
        # Tenta obter do banco, senão usa coordenadas padrão de Palmas-TO
        if self.store and hasattr(self.store, 'latitude') and self.store.latitude:
            return {
                'lat': float(self.store.latitude),
                'lng': float(self.store.longitude)
            }
        # Coordenadas padrão: centro de Palmas-TO
        return {'lat': -10.1849, 'lng': -48.3346}
    
    # ========================================================================
    # HANDLERS
    # ========================================================================
    
    def _handle_greeting(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Saudação inicial."""
        return OrchestratorResponse(
            content="👋 *Olá! Bem-vindo à Pastita!*\n\nSou seu assistente virtual e vou te ajudar com seu pedido. 🍝\n\nO que você gostaria de fazer?",
            source=ResponseSource.HANDLER,
            intent=IntentType.GREETING,
            buttons=[
                {'id': 'menu', 'title': '📋 Ver Cardápio'},
                {'id': 'hours', 'title': '🕐 Horários'},
            ]
        )
    
    def _handle_menu(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Mostra cardápio."""
        from apps.stores.models import StoreProduct
        
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        ).order_by('sort_order')[:10]
        
        if not products:
            return OrchestratorResponse(
                content="❌ Cardápio não disponível no momento.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.MENU_REQUEST
            )
        
        lines = ["📋 *Cardápio Pastita*\n", "Escolha seus produtos:\n"]
        
        for i, product in enumerate(products, 1):
            price = getattr(product, 'price', getattr(product, 'base_price', 0))
            lines.append(f"*{i}* - {product.name}")
            lines.append(f"    R$ {price:.2f}")
            if hasattr(product, 'description') and product.description:
                lines.append(f"    _{product.description[:50]}..._")
            lines.append("")
        
        lines.append("_Digite o número ou nome do produto_")
        
        return OrchestratorResponse(
            content="\n".join(lines),
            source=ResponseSource.HANDLER,
            intent=IntentType.MENU_REQUEST,
            buttons=[
                {'id': 'cart', 'title': '🛒 Ver Carrinho'},
            ]
        )
    
    def _handle_add_to_cart(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Adiciona item ao carrinho."""
        from apps.stores.models import StoreProduct
        
        quantity = 1
        product_name = message
        
        qty_match = re.match(r'(\d+)\s+(.+)', message.lower())
        if qty_match:
            quantity = int(qty_match.group(1))
            product_name = qty_match.group(2)
        
        product = StoreProduct.objects.filter(
            store=self.store,
            name__icontains=product_name,
            is_active=True
        ).first()
        
        if not product:
            return OrchestratorResponse(
                content=f"❌ Produto não encontrado: *{product_name}*\n\nDigite *cardápio* para ver as opções.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.ADD_TO_CART
            )
        
        if not session.cart_data:
            session.cart_data = {'items': []}
        
        price = getattr(product, 'price', getattr(product, 'base_price', 0))
        
        session.cart_data['items'].append({
            'product_id': str(product.id),
            'name': product.name,
            'quantity': quantity,
            'price': str(price)
        })
        
        session.cart_total = sum(
            Decimal(item['price']) * item['quantity']
            for item in session.cart_data['items']
        )
        session.cart_items_count = sum(item['quantity'] for item in session.cart_data['items'])
        session.status = 'cart_created'
        session.save()
        
        return OrchestratorResponse(
            content=f"✅ *{quantity}x {product.name}* adicionado!\n\n🛒 Total: R$ {session.cart_total:.2f}",
            source=ResponseSource.HANDLER,
            intent=IntentType.ADD_TO_CART,
            buttons=[
                {'id': 'cart', 'title': '🛒 Ver Carrinho'},
                {'id': 'menu', 'title': '📋 Continuar'},
            ]
        )
    
    def _handle_view_cart(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Mostra carrinho."""
        if not session.cart_data or not session.cart_data.get('items'):
            return OrchestratorResponse(
                content="🛒 *Carrinho vazio*\n\nDigite *cardápio* para ver opções!",
                source=ResponseSource.HANDLER,
                intent=IntentType.VIEW_CART,
                buttons=[
                    {'id': 'menu', 'title': '📋 Ver Cardápio'},
                ]
            )
        
        lines = ["🛒 *Seu Carrinho*\n"]
        
        for item in session.cart_data['items']:
            subtotal = Decimal(item['price']) * item['quantity']
            lines.append(f"• {item['quantity']}x {item['name']} - R$ {subtotal:.2f}")
        
        lines.append(f"\n*Total: R$ {session.cart_total:.2f}*")
        lines.append("\n_Digite *finalizar* para concluir_")
        
        return OrchestratorResponse(
            content="\n".join(lines),
            source=ResponseSource.HANDLER,
            intent=IntentType.VIEW_CART,
            buttons=[
                {'id': 'checkout', 'title': '✅ Finalizar'},
                {'id': 'menu', 'title': '📋 Adicionar Mais'},
            ]
        )
    
    def _handle_clear_cart(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Limpa carrinho."""
        session.cart_data = {'items': []}
        session.cart_total = Decimal('0')
        session.cart_items_count = 0
        session.save()
        
        return OrchestratorResponse(
            content="🗑️ *Carrinho limpo!*\n\nDigite *cardápio* para começar.",
            source=ResponseSource.HANDLER,
            intent=IntentType.CLEAR_CART,
            buttons=[
                {'id': 'menu', 'title': '📋 Ver Cardápio'},
            ]
        )
    
    def _handle_create_order(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Inicia processo de finalização - pergunta entrega/retirada."""
        if not session.cart_data or not session.cart_data.get('items'):
            return OrchestratorResponse(
                content="❌ Carrinho vazio.\n\nDigite *cardápio* primeiro.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.CREATE_ORDER
            )
        
        session.status = 'awaiting_delivery_method'
        session.save()
        
        return OrchestratorResponse(
            content="🚚 *Como deseja receber?*\n\nEscolha uma opção:",
            source=ResponseSource.HANDLER,
            intent=IntentType.DELIVERY_METHOD,
            buttons=[
                {'id': 'delivery', 'title': '🛵 Entrega'},
                {'id': 'pickup', 'title': '🏪 Retirada'},
            ]
        )
    
    def _handle_delivery_method_selection(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Processa seleção de entrega/retirada."""
        message_lower = message.lower().strip()
        
        if message_lower in ['entrega', 'delivery', '1', '🛵']:
            session.delivery_method = 'delivery'
            session.status = 'awaiting_address'
            session.save()
            
            return OrchestratorResponse(
                content="📍 *Informe seu endereço completo:*\n\nExemplo: _Rua das Flores, 123, Centro, Palmas-TO_",
                source=ResponseSource.HANDLER,
                intent=IntentType.DELIVERY_ADDRESS
            )
        
        elif message_lower in ['retirada', 'pickup', '2', '🏪', 'buscar']:
            session.delivery_method = 'pickup'
            session.status = 'awaiting_payment_method'
            session.save()
            
            return OrchestratorResponse(
                content="🏪 *Retirada na loja*\n\nComo deseja pagar?",
                source=ResponseSource.HANDLER,
                intent=IntentType.PAYMENT_METHOD,
                buttons=[
                    {'id': 'pay_pickup', 'title': '💵 Pagar na Retirada'},
                    {'id': 'pay_pix', 'title': '💳 PIX'},
                ]
            )
        
        return OrchestratorResponse(
            content="❌ Opção não reconhecida.\n\nDigite *entrega* ou *retirada*.",
            source=ResponseSource.FALLBACK,
            intent=IntentType.DELIVERY_METHOD
        )
    
    def _handle_address_input(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Processa endereço de entrega."""
        address_data = self.here_api.geocode_address(message)
        
        if not address_data:
            return OrchestratorResponse(
                content="❌ Endereço não encontrado.\n\nFormato: _Rua, Número, Bairro, Cidade-UF_",
                source=ResponseSource.FALLBACK,
                intent=IntentType.DELIVERY_ADDRESS
            )
        
        store_location = self._get_store_location()
        route = self.here_api.calculate_route(
            (store_location['lat'], store_location['lng']),
            (address_data['lat'], address_data['lng'])
        )
        
        if route:
            distance_km = route['distance_km']
            delivery_fee = self.here_api.calculate_delivery_fee(distance_km)
            
            session.delivery_address = address_data['address']
            session.distance_km = distance_km
            session.delivery_fee = delivery_fee
            session.status = 'awaiting_payment_method'
            session.save()
            
            total_with_delivery = session.cart_total + delivery_fee
            
            return OrchestratorResponse(
                content=f"📍 *Endereço:* {address_data['address']}\n📏 Distância: {distance_km} km\n🛵 Taxa: R$ {delivery_fee:.2f}\n\n💰 *Total: R$ {total_with_delivery:.2f}*\n\nComo deseja pagar?",
                source=ResponseSource.HANDLER,
                intent=IntentType.PAYMENT_METHOD,
                buttons=[
                    {'id': 'pay_delivery', 'title': '💵 Pagar na Entrega'},
                    {'id': 'pay_pix', 'title': '💳 PIX'},
                ]
            )
        else:
            session.delivery_address = address_data['address']
            session.status = 'awaiting_payment_method'
            session.save()
            
            return OrchestratorResponse(
                content=f"📍 *Endereço:* {address_data['address']}\n💰 *Total: R$ {session.cart_total:.2f}*\n\nComo deseja pagar?",
                source=ResponseSource.HANDLER,
                intent=IntentType.PAYMENT_METHOD,
                buttons=[
                    {'id': 'pay_delivery', 'title': '💵 Pagar na Entrega'},
                    {'id': 'pay_pix', 'title': '💳 PIX'},
                ]
            )
    
    def _handle_payment_method_selection(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Processa seleção de método de pagamento."""
        message_lower = message.lower().strip()
        
        if message_lower in ['pix', 'pagar pix', '2', '💳']:
            session.payment_method = 'pix'
            session.status = 'checkout'
            session.save()
            return self._create_order_and_generate_pix(session)
        
        elif message_lower in ['dinheiro', 'pagar na entrega', 'pagar na retirada', '1', '💵']:
            session.payment_method = 'cash'
            session.status = 'checkout'
            session.save()
            return self._create_order_cash(session)
        
        elif message_lower in ['cartão', 'cartao', 'máquina', 'maquina', '3']:
            session.payment_method = 'card'
            session.status = 'checkout'
            session.save()
            return self._create_order_card(session)
        
        return OrchestratorResponse(
            content="❌ Opção não reconhecida.\n\nDigite *PIX*, *dinheiro* ou *cartão*.",
            source=ResponseSource.FALLBACK,
            intent=IntentType.PAYMENT_METHOD
        )
    
    def _create_order_and_generate_pix(self, session) -> OrchestratorResponse:
        """Cria pedido e gera PIX."""
        from apps.stores.models import StoreOrder, StoreOrderItem, StorePayment
        
        total = session.cart_total
        if session.delivery_fee:
            total += session.delivery_fee
        
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name=self.conversation.contact_name or 'Cliente',
            customer_phone=self.conversation.phone_number,
            status='pending',
            payment_status='pending',
            delivery_method=session.delivery_method,
            delivery_address=session.delivery_address,
            delivery_fee=session.delivery_fee or Decimal('0'),
            subtotal=session.cart_total,
            total=total
        )
        
        for item_data in session.cart_data['items']:
            StoreOrderItem.objects.create(
                order=order,
                product_id=item_data.get('product_id'),
                product_name=item_data.get('name', 'Produto'),
                quantity=item_data.get('quantity', 1),
                unit_price=Decimal(item_data.get('price', '0')),
                subtotal=Decimal(item_data.get('price', '0')) * item_data.get('quantity', 1)
            )
        
        session.order_id = str(order.id)
        session.status = 'awaiting_payment'
        session.save()
        
        return self._generate_pix_for_order(order, session)
    
    def _create_order_cash(self, session) -> OrchestratorResponse:
        """Cria pedido com pagamento em dinheiro."""
        from apps.stores.models import StoreOrder, StoreOrderItem
        
        total = session.cart_total
        if session.delivery_fee:
            total += session.delivery_fee
        
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name=self.conversation.contact_name or 'Cliente',
            customer_phone=self.conversation.phone_number,
            status='confirmed',
            payment_status='pending',
            delivery_method=session.delivery_method,
            delivery_address=session.delivery_address,
            delivery_fee=session.delivery_fee or Decimal('0'),
            payment_method='cash',
            subtotal=session.cart_total,
            total=total
        )
        
        for item_data in session.cart_data['items']:
            StoreOrderItem.objects.create(
                order=order,
                product_id=item_data.get('product_id'),
                product_name=item_data.get('name', 'Produto'),
                quantity=item_data.get('quantity', 1),
                unit_price=Decimal(item_data.get('price', '0')),
                subtotal=Decimal(item_data.get('price', '0')) * item_data.get('quantity', 1)
            )
        
        session.order_id = str(order.id)
        session.status = 'order_confirmed'
        session.save()
        
        delivery_text = "será entregue" if session.delivery_method == 'delivery' else "estará pronto para retirada"
        
        return OrchestratorResponse(
            content=f"✅ *Pedido confirmado!*\n\nNúmero: *{order.order_number}*\nTotal: R$ {order.total:.2f}\nPagamento: Dinheiro\n\nSeu pedido {delivery_text} em breve!\n\nObrigado pela preferência! 🍝",
            source=ResponseSource.HANDLER,
            intent=IntentType.CONFIRM_ORDER,
            buttons=[
                {'id': 'status', 'title': '📊 Status do Pedido'},
            ]
        )
    
    def _create_order_card(self, session) -> OrchestratorResponse:
        """Cria pedido com pagamento em cartão."""
        from apps.stores.models import StoreOrder, StoreOrderItem
        
        total = session.cart_total
        if session.delivery_fee:
            total += session.delivery_fee
        
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name=self.conversation.contact_name or 'Cliente',
            customer_phone=self.conversation.phone_number,
            status='confirmed',
            payment_status='pending',
            delivery_method=session.delivery_method,
            delivery_address=session.delivery_address,
            delivery_fee=session.delivery_fee or Decimal('0'),
            payment_method='card',
            subtotal=session.cart_total,
            total=total
        )
        
        for item_data in session.cart_data['items']:
            StoreOrderItem.objects.create(
                order=order,
                product_id=item_data.get('product_id'),
                product_name=item_data.get('name', 'Produto'),
                quantity=item_data.get('quantity', 1),
                unit_price=Decimal(item_data.get('price', '0')),
                subtotal=Decimal(item_data.get('price', '0')) * item_data.get('quantity', 1)
            )
        
        session.order_id = str(order.id)
        session.status = 'order_confirmed'
        session.save()
        
        delivery_text = "será entregue" if session.delivery_method == 'delivery' else "estará pronto para retirada"
        
        return OrchestratorResponse(
            content=f"✅ *Pedido confirmado!*\n\nNúmero: *{order.order_number}*\nTotal: R$ {order.total:.2f}\nPagamento: Cartão\n\nSeu pedido {delivery_text} em breve!\n\nObrigado! 🍝",
            source=ResponseSource.HANDLER,
            intent=IntentType.CONFIRM_ORDER,
            buttons=[
                {'id': 'status', 'title': '📊 Status do Pedido'},
            ]
        )
    
    def _generate_pix_for_order(self, order, session) -> OrchestratorResponse:
        """Gera PIX para o pedido."""
        from apps.stores.models import StorePayment, StorePaymentGateway
        
        try:
            import mercadopago
            
            access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
            if not access_token:
                return OrchestratorResponse(
                    content="💳 Sistema de pagamentos em configuração.\n\nTente novamente mais tarde.",
                    source=ResponseSource.FALLBACK,
                    intent=IntentType.REQUEST_PIX
                )
            
            sdk = mercadopago.SDK(access_token)
            
            payment_data = {
                "transaction_amount": float(order.total),
                "description": f"Pedido {order.order_number} - Pastita",
                "payment_method_id": "pix",
                "payer": {
                    "email": "cliente@pastita.com.br",
                    "first_name": order.customer_name or "Cliente",
                },
                "external_reference": order.order_number,
            }
            
            payment_response = sdk.payment().create(payment_data)
            
            if payment_response["status"] == 201:
                payment_info = payment_response["response"]
                pix_code = payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
                payment_id = payment_info.get("id", "")
                
                gateway = StorePaymentGateway.objects.filter(
                    store=self.store,
                    gateway_type='mercadopago'
                ).first()
                
                payment = StorePayment.objects.create(
                    order=order,
                    gateway=gateway,
                    amount=order.total,
                    payment_method='pix',
                    payer_name=order.customer_name,
                    payer_email="cliente@pastita.com.br",
                    external_id=str(payment_id),
                    pix_code=pix_code,
                    gateway_response=payment_info,
                    status='pending'
                )
                
                session.payment_id = str(payment.id)
                session.pix_code = pix_code
                session.pix_expires_at = payment_info.get("date_of_expiration")
                session.save()
                
                return OrchestratorResponse(
                    content=f"💳 *Código PIX gerado!*\n\nPedido: *{order.order_number}*\nTotal: R$ {order.total:.2f}\n\n*Código:*\n`{pix_code}`\n\n_Válido por 30 minutos_\n\nDepois de pagar, envie *paguei* aqui!",
                    source=ResponseSource.HANDLER,
                    intent=IntentType.REQUEST_PIX
                )
            else:
                logger.error(f"Erro PIX: {payment_response}")
                return OrchestratorResponse(
                    content="❌ Erro ao gerar PIX.\n\nTente novamente ou escolha outro método.",
                    source=ResponseSource.FALLBACK,
                    intent=IntentType.REQUEST_PIX
                )
                
        except Exception as e:
            logger.exception(f"Erro PIX: {e}")
            return OrchestratorResponse(
                content="💳 Erro técnico.\n\nTente novamente em alguns minutos.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
    
    def _handle_request_pix(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Handler para solicitação de PIX."""
        if not session.order_id:
            return OrchestratorResponse(
                content="❌ Crie um pedido primeiro.\n\nDigite *finalizar*.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
        
        from apps.stores.models import StoreOrder
        try:
            order = StoreOrder.objects.get(id=session.order_id)
            return self._generate_pix_for_order(order, session)
        except StoreOrder.DoesNotExist:
            return OrchestratorResponse(
                content="❌ Pedido não encontrado.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
    
    def _handle_confirm_payment(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Processa confirmação de pagamento."""
        from apps.stores.models import StoreOrder, StorePayment
        
        if not session.order_id:
            return OrchestratorResponse(
                content="❌ Nenhum pedido em andamento.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.CONFIRM_PAYMENT
            )
        
        try:
            order = StoreOrder.objects.get(id=session.order_id)
            
            # Atualiza status do pedido
            order.payment_status = 'confirmed'
            order.status = 'confirmed'
            order.save()
            
            # Atualiza pagamento se existir
            if session.payment_id:
                try:
                    payment = StorePayment.objects.get(id=session.payment_id)
                    payment.status = 'completed'
                    payment.save()
                except StorePayment.DoesNotExist:
                    pass
            
            session.status = 'order_confirmed'
            session.save()
            
            delivery_text = "será entregue" if order.delivery_method == 'delivery' else "estará pronto para retirada"
            
            return OrchestratorResponse(
                content=f"✅ *Pagamento confirmado!*\n\nPedido: *{order.order_number}*\n\nSeu pedido {delivery_text} em breve!\n\nAgradecemos a preferência! 🍝",
                source=ResponseSource.HANDLER,
                intent=IntentType.CONFIRM_PAYMENT,
                buttons=[
                    {'id': 'status', 'title': '📊 Status'},
                ]
            )
            
        except StoreOrder.DoesNotExist:
            return OrchestratorResponse(
                content="❌ Pedido não encontrado.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.CONFIRM_PAYMENT
            )
    
    def _handle_cancel_order(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Cancela pedido."""
        from apps.stores.models import StoreOrder
        
        if session.order_id:
            try:
                order = StoreOrder.objects.get(id=session.order_id)
                order.status = 'cancelled'
                order.save()
            except StoreOrder.DoesNotExist:
                pass
        
        session.cart_data = {'items': []}
        session.cart_total = Decimal('0')
        session.order_id = None
        session.payment_id = None
        session.status = 'active'
        session.save()
        
        return OrchestratorResponse(
            content="❌ Pedido cancelado.\n\nDigite *cardápio* para começar novamente.",
            source=ResponseSource.HANDLER,
            intent=IntentType.CANCEL_ORDER,
            buttons=[
                {'id': 'menu', 'title': '📋 Cardápio'},
            ]
        )
    
    def _handle_human_handoff(self, message: str, data: Dict, session) -> OrchestratorResponse:
        """Transferência para atendente."""
        session.status = 'human_handoff'
        session.save()
        
        return OrchestratorResponse(
            content="👨‍💼 *Transferindo para atendente...*\n\nUm de nossos atendentes vai te atender em breve.\n\nPor favor, aguarde.",
            source=ResponseSource.HANDLER,
            intent=IntentType.HUMAN_HANDOFF
        )
    
    def _fallback_response(self, message: str) -> OrchestratorResponse:
        """Resposta padrão para mensagens não reconhecidas."""
        return OrchestratorResponse(
            content="🤔 Não entendi.\n\nDigite *cardápio* para ver opções ou *atendente* para falar com uma pessoa.",
            source=ResponseSource.FALLBACK,
            intent=IntentType.UNKNOWN,
            buttons=[
                {'id': 'menu', 'title': '📋 Cardápio'},
                {'id': 'human', 'title': '👨‍💼 Atendente'},
            ]
        )
