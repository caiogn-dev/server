"""
Pastita Orchestrator - Versão Estável sem dependência de LLM externo
Usa regex para intents e respostas rápidas locais.
"""
import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)


# =============================================================================
# HERE API SERVICE - Geocoding e Routing
# =============================================================================

class HereApiService:
    """Serviço de integração com HERE API para geocoding e cálculo de rotas."""
    
    def __init__(self):
        self.api_key = getattr(settings, 'HERE_API_KEY', '')
        self.geocode_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.route_url = "https://router.hereapi.com/v8/routes"
    
    def geocode_address(self, address: str) -> Optional[Dict]:
        """Converte endereço em coordenadas geográficas."""
        if not self.api_key:
            logger.warning("HERE_API_KEY não configurada")
            return None
        
        try:
            import requests
            
            params = {
                'q': address,
                'apiKey': self.api_key,
                'limit': 1
            }
            
            response = requests.get(self.geocode_url, params=params, timeout=3)
            response.raise_for_status()
            
            data = response.json()
            if data.get('items'):
                item = data['items'][0]
                position = item.get('position', {})
                address_data = item.get('address', {})
                
                return {
                    'formatted_address': item.get('title', address),
                    'lat': position.get('lat'),
                    'lng': position.get('lng'),
                    'street': address_data.get('street'),
                    'house_number': address_data.get('houseNumber'),
                    'district': address_data.get('district'),
                    'city': address_data.get('city'),
                    'state': address_data.get('state'),
                    'postal_code': address_data.get('postalCode'),
                }
            return None
            
        except Exception as e:
            logger.error(f"Erro ao geocodificar endereço: {e}")
            return None
    
    def calculate_route(self, origin_lat: float, origin_lng: float, 
                       dest_lat: float, dest_lng: float) -> Optional[Dict]:
        """Calcula distância e tempo entre dois pontos."""
        if not self.api_key:
            return None
        
        try:
            import requests
            
            params = {
                'transportMode': 'car',
                'origin': f"{origin_lat},{origin_lng}",
                'destination': f"{dest_lat},{dest_lng}",
                'return': 'summary',
                'apiKey': self.api_key
            }
            
            response = requests.get(self.route_url, params=params, timeout=3)
            response.raise_for_status()
            
            data = response.json()
            if data.get('routes'):
                route = data['routes'][0]
                section = route.get('sections', [{}])[0]
                summary = section.get('summary', {})
                
                distance_m = summary.get('length', 0)
                duration_s = summary.get('duration', 0)
                
                return {
                    'distance_m': distance_m,
                    'distance_km': round(distance_m / 1000, 2),
                    'duration_min': round(duration_s / 60, 0),
                    'duration_text': f"{int(duration_s // 60)} min",
                }
            return None
            
        except Exception as e:
            logger.error(f"Erro ao calcular rota: {e}")
            return None
    
    def calculate_delivery_fee(self, distance_km: float) -> Decimal:
        """Calcula taxa de entrega baseada na distância.
        
        Regras:
        - Até 3km: R$ 5,00
        - De 3km a 5km: R$ 5,00 + R$ 1,50/km
        - Acima de 5km: R$ 8,00 + R$ 2,00/km
        """
        base_fee = Decimal('5.00')
        
        if distance_km <= 3:
            return base_fee
        elif distance_km <= 5:
            additional = (distance_km - 3) * Decimal('1.50')
            return base_fee + additional
        else:
            base_fee = Decimal('8.00')
            additional = (distance_km - 5) * Decimal('2.00')
            return base_fee + additional


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
    REQUEST_PIX = "request_pix"
    CONFIRM_PAYMENT = "confirm_payment"
    ORDER_STATUS = "order_status"
    BUSINESS_HOURS = "business_hours"
    DELIVERY_INFO = "delivery_info"
    HUMAN_HANDOFF = "human_handoff"
    # Novos intents para fluxo completo
    SELECT_DELIVERY_METHOD = "select_delivery_method"
    PROVIDE_ADDRESS = "provide_address"
    SELECT_PAYMENT_METHOD = "select_payment_method"
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


class IntentDetector:
    """Detector de intenções usando regex - rápido e confiável."""
    
    PATTERNS = {
        IntentType.GREETING: [
            r'^(oi|ol[áa]|ola|eae|eai|bom dia|boa tarde|boa noite|salve|hey|hi|hello|opa|tudo bem|como vai)',
        ],
        IntentType.MENU_REQUEST: [
            r'(card[áa]pio|menu|o que (tem|voc[êe]s t[êe]m)|op[çc][õo]es|produtos|ver produtos)',
        ],
        IntentType.PRODUCT_INQUIRY: [
            r'(quanto custa|qual [o ]?pre[çc]o|valor do|pre[çc]o do|informa[çc][õo]es sobre)',
        ],
        IntentType.ADD_TO_CART: [
            r'(quero|vou querer|adiciona|coloca|me v[êe]|pedir|gostaria de)',
            r'(\d+\s+(rondelli|lasanha|nhoque|talharim|fettuccine|molho))',
        ],
        IntentType.REMOVE_FROM_CART: [
            r'(tira|remove|retira|tirar|remover|cancela)',
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
        IntentType.CONFIRM_ORDER: [
            r'(confirmo|tudo certo|pode seguir|ok|sim|confirmar)',
        ],
        IntentType.CANCEL_ORDER: [
            r'(cancela|n[ãa]o quero mais|desistir|cancelar)',
        ],
        IntentType.REQUEST_PIX: [
            r'(pix|gerar pix|c[óo]digo|qr code|como pagar|pagar|pagamento)',
        ],
        IntentType.CONFIRM_PAYMENT: [
            r'(paguei|j[áa] paguei|comprovante|enviei|transferi|pago)',
        ],
        IntentType.ORDER_STATUS: [
            r'(status|onde est[áa]|rastrear|rastreio|acompanhar|meu pedido)',
        ],
        IntentType.BUSINESS_HOURS: [
            r'(hor[áa]rio|que horas|abre|fecha|funcionamento|aberto)',
        ],
        IntentType.DELIVERY_INFO: [
            r'(entrega|frete|delivery|envia|taxa|tempo de entrega|receber)',
        ],
        IntentType.HUMAN_HANDOFF: [
            r'(atendente|humano|falar com pessoa|reclamar|suporte)',
        ],
    }
    
    def detect(self, message: str) -> tuple[IntentType, Dict]:
        """Detecta a intenção da mensagem."""
        message_lower = message.lower().strip()
        
        for intent, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    return intent, {'confidence': 0.95}
        
        # Tenta extrair quantidade + produto
        quantity_pattern = r'(\d+)\s+(?:unidades?|uni|por[çc][õo]es?|pratos?|potes?)?\s*(?:de\s+)?(.+)'
        match = re.search(quantity_pattern, message_lower, re.IGNORECASE)
        if match:
            return IntentType.ADD_TO_CART, {
                'quantity': int(match.group(1)),
                'product_name': match.group(2).strip(),
                'confidence': 0.9
            }
        
        # Padrão: número + produto (ex: "2 rondelli de frango")
        simple_qty_pattern = r'^(\d+)\s+(.+)$'
        match = re.search(simple_qty_pattern, message_lower, re.IGNORECASE)
        if match:
            potential_product = match.group(2).strip()
            if any(word in potential_product for word in ['rondelli', 'lasanha', 'nhoque', 'talharim', 'fettuccine', 'molho']):
                return IntentType.ADD_TO_CART, {
                    'quantity': int(match.group(1)),
                    'product_name': potential_product,
                    'confidence': 0.9
                }
        
        # Padrão simples: só o nome do produto
        simple_product = r'^(rondelli|lasanha|nhoque|talharim|fettuccine|molho)'
        if re.search(simple_product, message_lower, re.IGNORECASE):
            return IntentType.ADD_TO_CART, {
                'product_name': message_lower,
                'confidence': 0.8
            }
        
        return IntentType.UNKNOWN, {'confidence': 0.0}


class PastitaOrchestrator:
    """Orquestrador estável - sem dependência de LLM externo."""
    
    def __init__(self, account, conversation, debug: bool = False):
        self.account = account
        self.conversation = conversation
        self.debug = debug
        self.detector = IntentDetector()
        self.store = self._get_store()
    
    def _get_store(self):
        """Busca a loja associada."""
        from apps.stores.models import Store
        if hasattr(self.account, 'stores'):
            store = self.account.stores.first()
            if store:
                return store
        return Store.objects.filter(slug='pastita').first()
    
    def _find_product(self, search_term: str):
        """Busca produto com múltiplas estratégias."""
        from apps.stores.models import StoreProduct
        
        search_term = search_term.strip()
        
        # 1. Busca exata
        product = StoreProduct.objects.filter(
            store=self.store,
            is_active=True,
            name__iexact=search_term
        ).first()
        
        # 2. Busca contém
        if not product:
            product = StoreProduct.objects.filter(
                store=self.store,
                is_active=True,
                name__icontains=search_term
            ).first()
        
        # 3. Busca por palavras-chave
        if not product:
            words = [w for w in search_term.split() if len(w) > 2]
            if words:
                query = Q()
                for word in words:
                    query |= Q(name__icontains=word)
                product = StoreProduct.objects.filter(
                    store=self.store,
                    is_active=True
                ).filter(query).first()
        
        return product
    
    def _get_company(self):
        """Busca a company padrão."""
        from apps.automation.models import CompanyProfile
        company = CompanyProfile.objects.filter(_company_name__icontains='pastita').first()
        if not company:
            company = CompanyProfile.objects.first()
        return company
    
    def process_message(self, message_text: str) -> OrchestratorResponse:
        """Processa mensagem do cliente."""
        if not message_text or not message_text.strip():
            return self._fallback_response("Não entendi. Pode repetir?")
        
        # Verifica estado da sessão primeiro para fluxos específicos
        from apps.automation.models import CustomerSession
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company
        ).order_by('-updated_at').first()
        
        # Se há uma sessão ativa em estado específico, usa handler apropriado
        if session and session.status:
            if session.status == 'awaiting_delivery_method':
                return self._handle_delivery_method_selection(message_text, {})
            elif session.status == 'awaiting_address':
                return self._handle_address_input(message_text, {})
            elif session.status == 'awaiting_payment_method':
                return self._handle_payment_method_selection(message_text, {})
        
        # Caso contrário, detecta intenção normalmente
        intent, intent_data = self.detector.detect(message_text.strip())
        
        if self.debug:
            logger.info(f"[Orchestrator] Intent: {intent.value}")
        
        # Roteia para handler
        handlers = {
            IntentType.GREETING: self._handle_greeting,
            IntentType.MENU_REQUEST: self._handle_menu,
            IntentType.PRODUCT_INQUIRY: self._handle_product_inquiry,
            IntentType.ADD_TO_CART: self._handle_add_to_cart,
            IntentType.VIEW_CART: self._handle_view_cart,
            IntentType.CREATE_ORDER: self._handle_create_order,
            IntentType.REQUEST_PIX: self._handle_request_pix,
            IntentType.HUMAN_HANDOFF: self._handle_human_handoff,
        }
        
        handler = handlers.get(intent, self._handle_unknown)
        
        try:
            response = handler(message_text, intent_data)
            response.intent = intent
            return response
        except Exception as e:
            logger.exception(f"[Orchestrator] Error: {e}")
            return self._fallback_response("Desculpe, tive um problema. Tente novamente ou digite 'atendente'.")
    
    # ===== HANDLERS =====
    
    def _handle_greeting(self, message: str, data: Dict) -> OrchestratorResponse:
        return OrchestratorResponse(
            content="👋 *Olá! Bem-vindo à Pastita!*\n\nSomos especialistas em massas artesanais. 🍝\n\n*Como posso ajudar?*\n• Ver *cardápio*\n• Fazer um *pedido*\n• Tirar *dúvidas*",
            source=ResponseSource.HANDLER,
            intent=IntentType.GREETING,
            buttons=[
                {'id': 'menu', 'title': '📋 Ver Cardápio'},
                {'id': 'cart', 'title': '🛒 Meu Carrinho'},
            ]
        )
    
    def _handle_menu(self, message: str, data: Dict) -> OrchestratorResponse:
        from apps.stores.models import StoreProduct
        
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        ).order_by('category__sort_order', 'sort_order', 'name')
        
        if not products:
            return self._fallback_response("Cardápio vazio no momento.")
        
        lines = ["📋 *NOSSO CARDÁPIO*\n"]
        current_category = None
        
        for p in products:
            cat_name = p.category.name if p.category else 'Geral'
            if cat_name != current_category:
                lines.append(f"\n*{cat_name}*")
                current_category = cat_name
            lines.append(f"• {p.name} - R$ {p.price:.2f}")
        
        lines.append("\n\n_Digite o nome do produto para adicionar ao carrinho_")
        
        return OrchestratorResponse(
            content="\n".join(lines),
            source=ResponseSource.HANDLER,
            intent=IntentType.MENU_REQUEST,
            buttons=[
                {'id': 'cart', 'title': '🛒 Ver Carrinho'},
                {'id': 'order', 'title': '✅ Finalizar'},
            ]
        )
    
    def _handle_product_inquiry(self, message: str, data: Dict) -> OrchestratorResponse:
        return OrchestratorResponse(
            content="Para ver nossos produtos e preços, digite *cardápio*.",
            source=ResponseSource.HANDLER,
            intent=IntentType.PRODUCT_INQUIRY
        )
    
    def _handle_add_to_cart(self, message: str, data: Dict) -> OrchestratorResponse:
        """Adiciona item ao carrinho."""
        from apps.automation.models import CustomerSession
        
        quantity = data.get('quantity', 1)
        product_name = data.get('product_name', message)
        
        # Limpa o nome do produto
        product_name = re.sub(r'^\d+\s*', '', product_name).strip()
        
        # Busca produto
        product = self._find_product(product_name)
        
        if not product:
            return OrchestratorResponse(
                content=f"❌ Não encontrei *{product_name}*.\n\nDigite *cardápio* para ver as opções disponíveis.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.ADD_TO_CART
            )
        
        # Busca ou cria sessão
        company = self._get_company()
        if not company:
            return self._fallback_response("Erro de configuração. Contate o suporte.")
        
        session, _ = CustomerSession.objects.get_or_create(
            phone_number=self.conversation.phone_number,
            company=company,
            defaults={'status': 'active', 'session_id': f'sess_{self.conversation.phone_number}'}
        )
        
        # Atualiza carrinho
        cart_data = session.cart_data or {'items': []}
        
        # Verifica se já existe
        existing = None
        for item in cart_data['items']:
            if item['product_id'] == str(product.id):
                existing = item
                break
        
        if existing:
            existing['quantity'] += quantity
        else:
            cart_data['items'].append({
                'product_id': str(product.id),
                'name': product.name,
                'quantity': quantity,
                'price': str(product.price),
                'notes': ''
            })
        
        # Calcula total
        total = sum(Decimal(i['price']) * i['quantity'] for i in cart_data['items'])
        item_count = sum(i['quantity'] for i in cart_data['items'])
        
        # Salva sessão
        session.cart_data = cart_data
        session.cart_total = total
        session.cart_items_count = item_count
        session.status = 'cart_created'
        session.save()
        
        return OrchestratorResponse(
            content=f"✅ *{quantity}x {product.name}* adicionado!\n\n🛒 Carrinho: {item_count} itens - R$ {total:.2f}\n\n_Digite *carrinho* para ver tudo ou *finalizar* para concluir_",
            source=ResponseSource.HANDLER,
            intent=IntentType.ADD_TO_CART,
            buttons=[
                {'id': 'menu', 'title': '📋 Continuar'},
                {'id': 'cart', 'title': '🛒 Carrinho'},
                {'id': 'checkout', 'title': '✅ Finalizar'},
            ]
        )
    
    def _handle_view_cart(self, message: str, data: Dict) -> OrchestratorResponse:
        """Mostra carrinho."""
        from apps.automation.models import CustomerSession
        
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company,
            status__in=['active', 'cart_created']
        ).order_by('-updated_at').first()
        
        if not session or not session.cart_data or not session.cart_data.get('items'):
            return OrchestratorResponse(
                content="🛒 *Seu carrinho está vazio*\n\nAdicione itens do nosso cardápio!\n\nDigite *cardápio* para ver as opções.",
                source=ResponseSource.HANDLER,
                intent=IntentType.VIEW_CART,
                buttons=[{'id': 'menu', 'title': '📋 Ver Cardápio'}]
            )
        
        lines = ["🛒 *Seu carrinho:*\n"]
        for i, item in enumerate(session.cart_data['items'], 1):
            subtotal = Decimal(item['price']) * item['quantity']
            lines.append(f"{i}. {item['name']}")
            lines.append(f"   {item['quantity']}x R$ {item['price']} = R$ {subtotal:.2f}")
        
        lines.append(f"\n*Total: R$ {session.cart_total:.2f}*")
        lines.append("\n_Digite *finalizar* para concluir o pedido_")
        
        return OrchestratorResponse(
            content="\n".join(lines),
            source=ResponseSource.HANDLER,
            intent=IntentType.VIEW_CART,
            buttons=[
                {'id': 'checkout', 'title': '✅ Finalizar Pedido'},
                {'id': 'menu', 'title': '📋 Adicionar Mais'},
            ]
        )
    
    def _handle_create_order(self, message: str, data: Dict) -> OrchestratorResponse:
        """Inicia processo de checkout - pergunta método de entrega."""
        from apps.automation.models import CustomerSession
        
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company,
            status__in=['active', 'cart_created']
        ).order_by('-updated_at').first()
        
        if not session or not session.cart_data or not session.cart_data.get('items'):
            return OrchestratorResponse(
                content="❌ Seu carrinho está vazio.\n\nAdicione itens primeiro! Digite *cardápio*.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.CREATE_ORDER
            )
        
        # NOVO FLUXO: Pergunta entrega ou retirada
        session.status = 'awaiting_delivery_method'
        session.save()
        
        return OrchestratorResponse(
            content="🚚 *Como deseja receber seu pedido?*\n\nEscolha uma opção:",
            source=ResponseSource.HANDLER,
            intent=IntentType.SELECT_DELIVERY_METHOD,
            buttons=[
                {'id': 'delivery', 'title': '🛵 Entrega'},
                {'id': 'pickup', 'title': '🏪 Retirada na Loja'},
            ]
        )
    
    def _handle_request_pix(self, message: str, data: Dict) -> OrchestratorResponse:
        """Gera PIX usando Mercado Pago."""
        from apps.automation.models import CustomerSession, CompanyProfile
        from apps.stores.models import StoreOrder, StorePayment, StorePaymentGateway
        from django.conf import settings
        
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company,
            status='checkout'
        ).order_by('-updated_at').first()
        
        if not session or not session.order_id:
            return OrchestratorResponse(
                content="❌ Você precisa criar um pedido primeiro.\n\nDigite *finalizar* para criar seu pedido.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
        
        try:
            order = StoreOrder.objects.get(id=session.order_id)
        except StoreOrder.DoesNotExist:
            return OrchestratorResponse(
                content="❌ Pedido não encontrado.\n\nDigite *finalizar* para criar um novo pedido.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
        
        # Verifica se já existe pagamento PIX para este pedido
        existing_payment = StorePayment.objects.filter(
            order=order,
            payment_method='pix'
        ).order_by('-created_at').first()
        
        if existing_payment and existing_payment.pix_code:
            # Retorna PIX existente
            return OrchestratorResponse(
                content=f"💳 *Código PIX gerado!*\n\nPedido: *{order.order_number}*\nTotal: R$ {order.total:.2f}\n\n*Código copia-e-cola:*\n`{existing_payment.pix_code}`\n\n_Valido por 30 minutos_",
                source=ResponseSource.HANDLER,
                intent=IntentType.REQUEST_PIX
            )
        
        # Gera novo PIX via Mercado Pago
        try:
            import mercadopago
            
            access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
            if not access_token:
                return OrchestratorResponse(
                    content="💳 *Pagamento via PIX*\n\nEstamos configurando o sistema de pagamentos.\n\n_Por favor, aguarde ou fale com um atendente._",
                    source=ResponseSource.HANDLER,
                    intent=IntentType.REQUEST_PIX
                )
            
            sdk = mercadopago.SDK(access_token)
            
            # Cria pagamento PIX
            payment_data = {
                "transaction_amount": float(order.total),
                "description": f"Pedido {order.order_number} - Pastita",
                "payment_method_id": "pix",
                "payer": {
                    "email": "cliente@pastita.com.br",
                    "first_name": order.customer_name or "Cliente",
                },
                "notification_url": f"{getattr(settings, 'BACKEND_URL', '')}/webhooks/v1/mercadopago",
                "external_reference": order.order_number,
            }
            
            payment_response = sdk.payment().create(payment_data)
            
            if payment_response["status"] == 201:
                payment_info = payment_response["response"]
                
                # Extrai dados do PIX
                pix_code = payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
                pix_qr_code = payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code_base64", "")
                payment_id = payment_info.get("id", "")
                
                # Salva pagamento no banco
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
                    pix_qr_code=pix_qr_code,
                    gateway_response=payment_info,
                    status='pending'
                )
                
                # Atualiza sessão
                session.payment_id = str(payment.id)
                session.pix_code = pix_code
                session.pix_expires_at = payment_info.get("date_of_expiration")
                session.save()
                
                # Monta resposta
                response_text = f"""💳 *Código PIX gerado!*

Pedido: *{order.order_number}*
Total: R$ {order.total:.2f}

*Código copia-e-cola:*
`{pix_code}`

_Valido por 30 minutos_

_Depois de pagar, envie o comprovante aqui!_"""
                
                return OrchestratorResponse(
                    content=response_text,
                    source=ResponseSource.HANDLER,
                    intent=IntentType.REQUEST_PIX
                )
            else:
                logger.error(f"Erro ao criar PIX: {payment_response}")
                return OrchestratorResponse(
                    content="❌ Erro ao gerar código PIX.\n\n_Tente novamente ou fale com um atendente._",
                    source=ResponseSource.FALLBACK,
                    intent=IntentType.REQUEST_PIX
                )
                
        except Exception as e:
            logger.exception(f"Erro ao gerar PIX: {e}")
            return OrchestratorResponse(
                content="💳 *Pagamento via PIX*\n\nEstamos com dificuldades técnicas.\n\n_Por favor, tente novamente em alguns minutos._",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
    
    # =================================================================
    # NOVOS HANDLERS PARA FLUXO COMPLETO DE ENTREGA E PAGAMENTO
    # =================================================================
    
    def _handle_delivery_method_selection(self, message: str, data: Dict) -> OrchestratorResponse:
        """Handler para seleção de entrega/retirada - chamado baseado no estado da sessão."""
        from apps.automation.models import CustomerSession
        
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company
        ).order_by('-updated_at').first()
        
        if not session:
            return self._handle_create_order(message, data)
        
        message_lower = message.lower().strip()
        
        # Verifica se é seleção de entrega
        if any(word in message_lower for word in ['entrega', 'delivery', 'receber', 'casa']):
            # Salva preferência e pede endereço
            session.delivery_method = 'delivery'
            session.status = 'awaiting_address'
            session.save()
            
            return OrchestratorResponse(
                content="📍 *Entrega selecionada*\n\nPor favor, informe seu endereço completo:\n\n_Exemplo: Rua das Flores, 123, Centro, Palmas-TO_",
                source=ResponseSource.HANDLER,
                intent=IntentType.SELECT_DELIVERY_METHOD
            )
        
        # Verifica se é seleção de retirada
        elif any(word in message_lower for word in ['retirada', 'pickup', 'buscar', 'loja']):
            session.delivery_method = 'pickup'
            session.status = 'awaiting_payment_method'
            session.save()
            
            return OrchestratorResponse(
                content="🏪 *Retirada na loja selecionada*\n\nComo deseja pagar?",
                source=ResponseSource.HANDLER,
                intent=IntentType.SELECT_DELIVERY_METHOD,
                buttons=[
                    {'id': 'pay_pickup', 'title': '💵 Pagar na Retirada'},
                    {'id': 'pay_pix', 'title': '💳 PIX (antecipado)'},
                ]
            )
        
        # Se não reconheceu, pergunta novamente
        return OrchestratorResponse(
            content="🚚 *Como deseja receber seu pedido?*\n\nEscolha uma opção:",
            source=ResponseSource.HANDLER,
            intent=IntentType.SELECT_DELIVERY_METHOD,
            buttons=[
                {'id': 'delivery', 'title': '🛵 Entrega'},
                {'id': 'pickup', 'title': '🏪 Retirada na Loja'},
            ]
        )
    
    def _handle_address_input(self, message: str, data: Dict) -> OrchestratorResponse:
        """Processa endereço de entrega usando HERE API para geocodificação."""
        from apps.automation.models import CustomerSession
        from apps.stores.models import Store
        
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company,
            status='awaiting_address'
        ).order_by('-updated_at').first()
        
        if not session:
            return OrchestratorResponse(
                content="❌ Sessão não encontrada.\n\nDigite *finalizar* para começar.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.PROVIDE_ADDRESS
            )
        
        # Inicializa serviço HERE API
        here_service = HereApiService()
        
        # Tenta geocodificar o endereço
        address_data = here_service.geocode_address(message)
        
        if address_data:
            # Endereço encontrado - usa endereço formatado
            formatted_address = address_data['formatted_address']
            session.delivery_address = formatted_address
            
            # Tenta calcular distância se tiver coordenadas da loja
            store_coords = self._get_store_coordinates()
            
            if store_coords and address_data.get('lat') and address_data.get('lng'):
                route = here_service.calculate_route(
                    store_coords['lat'], store_coords['lng'],
                    address_data['lat'], address_data['lng']
                )
                
                if route:
                    distance_km = route['distance_km']
                    delivery_fee = here_service.calculate_delivery_fee(distance_km)
                    
                    session.distance_km = distance_km
                    session.delivery_fee = delivery_fee
                    session.status = 'awaiting_payment_method'
                    session.save()
                    
                    total_with_delivery = session.cart_total + delivery_fee
                    
                    return OrchestratorResponse(
                        content=f"📍 *Endereço confirmado:*\n{formatted_address}\n\n"
                                f"📏 Distância: {distance_km} km\n"
                                f"🛵 Taxa de entrega: R$ {delivery_fee:.2f}\n"
                                f"⏱️ Tempo estimado: {route['duration_text']}\n\n"
                                f"💰 *Total com entrega: R$ {total_with_delivery:.2f}*\n\n"
                                f"Como deseja pagar?",
                        source=ResponseSource.HANDLER,
                        intent=IntentType.SELECT_PAYMENT_METHOD,
                        buttons=[
                            {'id': 'pay_delivery', 'title': '💵 Pagar na Entrega'},
                            {'id': 'pay_pix', 'title': '💳 PIX (antecipado)'},
                        ]
                    )
            
            # Se não conseguiu calcular rota, usa taxa fixa
            delivery_fee = Decimal('5.00')
            session.delivery_fee = delivery_fee
            session.status = 'awaiting_payment_method'
            session.save()
            
            total_with_delivery = session.cart_total + delivery_fee
            
            return OrchestratorResponse(
                content=f"📍 *Endereço confirmado:*\n{formatted_address}\n\n"
                        f"🛵 Taxa de entrega: R$ {delivery_fee:.2f}\n\n"
                        f"💰 *Total com entrega: R$ {total_with_delivery:.2f}*\n\n"
                        f"Como deseja pagar?",
                source=ResponseSource.HANDLER,
                intent=IntentType.SELECT_PAYMENT_METHOD,
                buttons=[
                    {'id': 'pay_delivery', 'title': '💵 Pagar na Entrega'},
                    {'id': 'pay_pix', 'title': '💳 PIX (antecipado)'},
                ]
            )
        else:
            # Endereço não encontrado - salva como texto e usa taxa fixa
            session.delivery_address = message
            delivery_fee = Decimal('5.00')
            session.delivery_fee = delivery_fee
            session.status = 'awaiting_payment_method'
            session.save()
            
            total_with_delivery = session.cart_total + delivery_fee
            
            return OrchestratorResponse(
                content=f"📍 *Endereço registrado:*\n{message}\n\n"
                        f"🛵 Taxa de entrega: R$ {delivery_fee:.2f}\n\n"
                        f"💰 *Total com entrega: R$ {total_with_delivery:.2f}*\n\n"
                        f"Como deseja pagar?",
                source=ResponseSource.HANDLER,
                intent=IntentType.SELECT_PAYMENT_METHOD,
                buttons=[
                    {'id': 'pay_delivery', 'title': '💵 Pagar na Entrega'},
                    {'id': 'pay_pix', 'title': '💳 PIX (antecipado)'},
                ]
            )
    
    def _get_store_coordinates(self) -> Optional[Dict]:
        """Obtém coordenadas da loja do banco de dados."""
        try:
            from apps.stores.models import Store
            
            store = Store.objects.filter(id=self.store.id).first() if self.store else None
            
            if store and hasattr(store, 'latitude') and hasattr(store, 'longitude'):
                if store.latitude and store.longitude:
                    return {
                        'lat': float(store.latitude),
                        'lng': float(store.longitude)
                    }
            
            # Coordenadas padrão de Palmas-TO (centro)
            return {'lat': -10.1849, 'lng': -48.3346}
            
        except Exception as e:
            logger.error(f"Erro ao obter coordenadas da loja: {e}")
            return {'lat': -10.1849, 'lng': -48.3346}
    
    def _handle_payment_method_selection(self, message: str, data: Dict) -> OrchestratorResponse:
        """Processa seleção de método de pagamento."""
        from apps.automation.models import CustomerSession
        from apps.stores.models import StoreOrder, StoreOrderItem
        
        company = self._get_company()
        session = CustomerSession.objects.filter(
            phone_number=self.conversation.phone_number,
            company=company,
            status='awaiting_payment_method'
        ).order_by('-updated_at').first()
        
        if not session or not session.cart_data:
            return OrchestratorResponse(
                content="❌ Carrinho vazio ou sessão inválida.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.SELECT_PAYMENT_METHOD
            )
        
        message_lower = message.lower().strip()
        
        # Calcula total com entrega se houver
        total = session.cart_total
        if session.delivery_fee:
            total += session.delivery_fee
        
        # Determina método de pagamento
        if any(word in message_lower for word in ['pix', '2']):
            payment_method = 'pix'
        elif any(word in message_lower for word in ['dinheiro', 'cash', 'entrega', 'retirada', '1']):
            payment_method = 'cash'
        elif any(word in message_lower for word in ['cartão', 'card', 'máquina', 'maquina', '3']):
            payment_method = 'card'
        else:
            # Se não reconheceu, pergunta novamente
            return OrchestratorResponse(
                content="💳 *Como deseja pagar?*\n\nEscolha uma opção:",
                source=ResponseSource.HANDLER,
                intent=IntentType.SELECT_PAYMENT_METHOD,
                buttons=[
                    {'id': 'pay_cash', 'title': '💵 Dinheiro'},
                    {'id': 'pay_card', 'title': '💳 Cartão'},
                    {'id': 'pay_pix', 'title': '📱 PIX'},
                ]
            )
        
        # Cria o pedido com método de pagamento
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name=self.conversation.contact_name or 'Cliente',
            customer_phone=self.conversation.phone_number,
            status='confirmed' if payment_method in ['cash', 'card'] else 'pending',
            payment_status='pending',
            delivery_method=session.delivery_method or 'pickup',
            delivery_address={'address': session.delivery_address} if session.delivery_address else {},
            delivery_fee=session.delivery_fee or Decimal('0'),
            subtotal=session.cart_total,
            total=total
        )
        
        # Cria itens do pedido
        for item_data in session.cart_data.get('items', []):
            StoreOrderItem.objects.create(
                order=order,
                product_id=item_data.get('product_id'),
                product_name=item_data.get('name', 'Produto'),
                quantity=item_data.get('quantity', 1),
                unit_price=Decimal(item_data.get('price', '0')),
                subtotal=Decimal(item_data.get('price', '0')) * item_data.get('quantity', 1)
            )
        
        # Atualiza sessão
        session.order_id = str(order.id)
        session.payment_method = payment_method
        session.status = 'checkout'
        session.save()
        
        # Resposta baseada no método de pagamento
        if payment_method == 'pix':
            # Gera PIX
            return self._generate_pix_for_order(order, session)
        else:
            # Pagamento na entrega/retirada
            method_text = 'dinheiro' if payment_method == 'cash' else 'cartão'
            delivery_text = 'entregue' if session.delivery_method == 'delivery' else 'pronto para retirada'
            
            return OrchestratorResponse(
                content=f"✅ *Pedido confirmado!*\n\nNúmero: *{order.order_number}*\nTotal: R$ {order.total:.2f}\nPagamento: {method_text.title()}\n\nSeu pedido será {delivery_text} em breve!\n\nObrigado pela preferência! 🍝",
                source=ResponseSource.HANDLER,
                intent=IntentType.CONFIRM_ORDER,
                buttons=[
                    {'id': 'status', 'title': '📊 Status do Pedido'},
                ]
            )
    
    def _generate_pix_for_order(self, order, session) -> OrchestratorResponse:
        """Gera PIX para o pedido - reutiliza código existente."""
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
                    gateway_response=payment_info,
                    status='pending'
                )
                
                # Atualizar o pedido com os dados do PIX
                order.pix_code = pix_code
                order.save(update_fields=['pix_code', 'updated_at'])
                
                session.payment_id = str(payment.id)
                session.pix_code = pix_code
                session.save()
                
                return OrchestratorResponse(
                    content=f"💳 *Código PIX gerado!*\n\nPedido: *{order.order_number}*\nTotal: R$ {order.total:.2f}\n\n*Código:*\n`{pix_code}`\n\n_Válido por 30 minutos_\n\nDepois de pagar, envie *paguei*!",
                    source=ResponseSource.HANDLER,
                    intent=IntentType.REQUEST_PIX
                )
            else:
                logger.error(f"Erro PIX: {payment_response}")
                return OrchestratorResponse(
                    content="❌ Erro ao gerar PIX.\n\nTente novamente.",
                    source=ResponseSource.FALLBACK,
                    intent=IntentType.REQUEST_PIX
                )
                
        except Exception as e:
            logger.exception(f"Erro PIX: {e}")
            return OrchestratorResponse(
                content="💳 Erro técnico. Tente novamente.",
                source=ResponseSource.FALLBACK,
                intent=IntentType.REQUEST_PIX
            )
    
    def _handle_human_handoff(self, message: str, data: Dict) -> OrchestratorResponse:
        return OrchestratorResponse(
            content="👨‍💼 *Transferindo para atendente humano...*\n\nUm de nossos atendentes vai te atender em breve.\n\nPor favor, aguarde.",
            source=ResponseSource.HANDLER,
            intent=IntentType.HUMAN_HANDOFF
        )
    
    def _handle_unknown(self, message: str, data: Dict) -> OrchestratorResponse:
        return OrchestratorResponse(
            content="Não entendi bem. Você pode:\n• Digitar *cardápio* para ver produtos\n• Digitar *carrinho* para ver seu pedido\n• Digitar *finalizar* para concluir\n• Digitar *atendente* para falar com uma pessoa",
            source=ResponseSource.FALLBACK,
            intent=IntentType.UNKNOWN
        )
    
    def _fallback_response(self, message: str) -> OrchestratorResponse:
        return OrchestratorResponse(
            content=message,
            source=ResponseSource.FALLBACK,
            intent=IntentType.UNKNOWN
        )
