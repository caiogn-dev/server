"""
Pastita Tools - Tools do sistema para uso com LangGraph.

Todas as tools são funções puras que interagem com os models e services existentes.
"""
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any
from langchain.tools import tool
from django.utils import timezone

logger = logging.getLogger(__name__)


@tool
def get_menu(store_id: str) -> str:
    """
    Retorna o cardápio atual da loja em formato de texto.
    
    Args:
        store_id: ID da loja (Store.uuid)
    
    Returns:
        String formatada com o cardápio organizado por categoria
    """
    try:
        from apps.stores.models import Store, StoreProduct
        
        store = Store.objects.filter(id=store_id).first()
        if not store:
            return "❌ Loja não encontrada."
        
        products = StoreProduct.objects.filter(
            store=store,
            status='active'
        ).select_related('category').order_by('category__sort_order', 'sort_order', 'name')
        
        if not products:
            return "📋 Cardápio vazio no momento."
        
        lines = [f"📋 *CARDÁPIO - {store.name}*\n"]
        current_category = None
        
        for product in products:
            cat_name = product.category.name if product.category else 'Geral'
            if cat_name != current_category:
                lines.append(f"\n*{cat_name}*")
                current_category = cat_name
            
            price_str = f"R$ {product.price:.2f}"
            if product.is_on_sale and product.compare_at_price:
                price_str = f"~~R$ {product.compare_at_price:.2f}~~ R$ {product.price:.2f}"
            
            stock_indicator = ""
            if product.track_stock and product.stock_quantity <= 0:
                stock_indicator = " (Indisponível)"
            elif product.track_stock and product.is_low_stock:
                stock_indicator = " (Poucas unidades)"
            
            lines.append(f"• {product.name} - {price_str}{stock_indicator}")
            if product.short_description:
                lines.append(f"  _{product.short_description[:50]}_")
        
        lines.append("\n\n_Digite o nome do produto para adicionar ao carrinho_")
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Erro ao buscar cardápio: {e}")
        return "❌ Erro ao carregar cardápio. Tente novamente."


@tool
def get_product_info(store_id: str, product_name: str) -> str:
    """
    Busca informações detalhadas de um produto específico.
    
    Args:
        store_id: ID da loja
        product_name: Nome ou parte do nome do produto
    
    Returns:
        Informações detalhadas do produto
    """
    try:
        from apps.stores.models import Store, StoreProduct
        from django.db.models import Q
        
        store = Store.objects.filter(id=store_id).first()
        if not store:
            return "❌ Loja não encontrada."
        
        # Busca por nome (case insensitive)
        product = StoreProduct.objects.filter(
            store=store,
            status='active'
        ).filter(
            Q(name__iexact=product_name) | Q(name__icontains=product_name)
        ).first()
        
        if not product:
            return f"❌ Produto '{product_name}' não encontrado. Digite 'cardápio' para ver as opções."
        
        lines = [
            f"*{product.name}*",
            f"",
            f"💰 Preço: R$ {product.price:.2f}",
        ]
        
        if product.is_on_sale and product.compare_at_price:
            lines.append(f"🏷️ ~~De: R$ {product.compare_at_price:.2f}~~")
            lines.append(f"✨ Por: R$ {product.price:.2f} ({product.discount_percentage}% OFF)")
        
        if product.description:
            lines.append(f"\n📝 {product.description}")
        
        if product.track_stock:
            if product.stock_quantity <= 0:
                lines.append(f"\n⚠️ *Produto indisponível no momento*")
            elif product.is_low_stock:
                lines.append(f"\n⚡ *Apenas {product.stock_quantity} unidades restantes!*")
            else:
                lines.append(f"\n✅ Disponível: {product.stock_quantity} unidades")
        
        if product.variants.exists():
            lines.append(f"\n*Opções disponíveis:*")
            for variant in product.variants.filter(is_active=True):
                price = variant.get_price()
                lines.append(f"  • {variant.name} - R$ {price:.2f}")
        
        lines.append(f"\n_Digite a quantidade e nome para adicionar ao carrinho_")
        lines.append(f"_Exemplo: '2 {product.name}'_")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Erro ao buscar produto: {e}")
        return "❌ Erro ao buscar informações do produto."


@tool
def add_to_cart(session_id: str, product_name: str, quantity: int = 1, notes: str = "") -> str:
    """
    Adiciona um item ao carrinho do cliente.
    
    Args:
        session_id: ID da sessão do cliente (CustomerSession.id)
        product_name: Nome do produto
        quantity: Quantidade (padrão: 1)
        notes: Observações especiais (opcional)
    
    Returns:
        Confirmação da adição ao carrinho
    """
    try:
        from apps.automation.models import CustomerSession
        from apps.stores.models import StoreProduct
        from decimal import Decimal
        import re
        
        session = CustomerSession.objects.filter(id=session_id).first()
        if not session:
            return "❌ Sessão não encontrada. Por favor, inicie uma nova conversa."
        
        # Busca produto
        product = StoreProduct.objects.filter(
            store=session.company.store,
            status='active',
            name__icontains=product_name
        ).first()
        
        if not product:
            return f"❌ Produto '{product_name}' não encontrado."
        
        # Verifica estoque
        if product.track_stock and product.stock_quantity < quantity:
            return f"❌ Estoque insuficiente. Disponível: {product.stock_quantity} unidades."
        
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
            if notes:
                existing['notes'] = notes
        else:
            cart_data['items'].append({
                'product_id': str(product.id),
                'name': product.name,
                'quantity': quantity,
                'price': str(product.price),
                'notes': notes
            })
        
        # Calcula totais
        total = sum(Decimal(i['price']) * i['quantity'] for i in cart_data['items'])
        item_count = sum(i['quantity'] for i in cart_data['items'])
        
        # Salva sessão
        session.cart_data = cart_data
        session.cart_total = total
        session.cart_items_count = item_count
        session.status = 'cart_created'
        session.save()
        
        return f"✅ *{quantity}x {product.name}* adicionado ao carrinho!\n\n🛒 Total: {item_count} itens - R$ {total:.2f}"
        
    except Exception as e:
        logger.error(f"Erro ao adicionar ao carrinho: {e}")
        return "❌ Erro ao adicionar item. Tente novamente."


@tool
def remove_from_cart(session_id: str, product_index: int) -> str:
    """
    Remove um item do carrinho pelo índice.
    
    Args:
        session_id: ID da sessão do cliente
        product_index: Índice do item no carrinho (1-based)
    
    Returns:
        Confirmação da remoção
    """
    try:
        from apps.automation.models import CustomerSession
        from decimal import Decimal
        
        session = CustomerSession.objects.filter(id=session_id).first()
        if not session:
            return "❌ Sessão não encontrada."
        
        cart_data = session.cart_data or {'items': []}
        items = cart_data.get('items', [])
        
        if not items:
            return "🛒 Seu carrinho está vazio."
        
        # Ajusta índice (1-based para 0-based)
        idx = product_index - 1
        
        if idx < 0 or idx >= len(items):
            return f"❌ Item {product_index} não encontrado. Digite 'carrinho' para ver os itens."
        
        removed_item = items.pop(idx)
        
        # Recalcula totais
        total = sum(Decimal(i['price']) * i['quantity'] for i in items)
        item_count = sum(i['quantity'] for i in items)
        
        # Salva sessão
        session.cart_data = cart_data
        session.cart_total = total
        session.cart_items_count = item_count
        session.save()
        
        return f"🗑️ *{removed_item['name']}* removido do carrinho.\n\n🛒 Total: {item_count} itens - R$ {total:.2f}"
        
    except Exception as e:
        logger.error(f"Erro ao remover do carrinho: {e}")
        return "❌ Erro ao remover item. Tente novamente."


@tool
def view_cart(session_id: str) -> str:
    """
    Mostra o conteúdo atual do carrinho.
    
    Args:
        session_id: ID da sessão do cliente
    
    Returns:
        Resumo do carrinho formatado
    """
    try:
        from apps.automation.models import CustomerSession
        from decimal import Decimal
        
        session = CustomerSession.objects.filter(id=session_id).first()
        if not session:
            return "❌ Sessão não encontrada."
        
        cart_data = session.cart_data or {'items': []}
        items = cart_data.get('items', [])
        
        if not items:
            return "🛒 *Seu carrinho está vazio*\n\nAdicione itens do cardápio! Digite 'cardápio' para ver as opções."
        
        lines = ["🛒 *Seu Carrinho:*\n"]
        
        for i, item in enumerate(items, 1):
            subtotal = Decimal(item['price']) * item['quantity']
            lines.append(f"{i}. {item['name']}")
            lines.append(f"   {item['quantity']}x R$ {item['price']} = R$ {subtotal:.2f}")
            if item.get('notes'):
                lines.append(f"   📝 {item['notes']}")
        
        lines.append(f"\n*Total: R$ {session.cart_total:.2f}*")
        lines.append(f"\n_Digite 'finalizar' para concluir ou o número do item para remover_")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Erro ao visualizar carrinho: {e}")
        return "❌ Erro ao carregar carrinho."


@tool
def clear_cart(session_id: str) -> str:
    """
    Limpa todos os itens do carrinho.
    
    Args:
        session_id: ID da sessão do cliente
    
    Returns:
        Confirmação da limpeza
    """
    try:
        from apps.automation.models import CustomerSession
        
        session = CustomerSession.objects.filter(id=session_id).first()
        if not session:
            return "❌ Sessão não encontrada."
        
        session.cart_data = {'items': []}
        session.cart_total = 0
        session.cart_items_count = 0
        session.save()
        
        return "🗑️ *Carrinho limpo!*\n\nSeu carrinho está vazio. Digite 'cardápio' para adicionar itens."
        
    except Exception as e:
        logger.error(f"Erro ao limpar carrinho: {e}")
        return "❌ Erro ao limpar carrinho."


@tool
def calculate_delivery_fee(store_id: str, address: str) -> Dict[str, Any]:
    """
    Calcula a taxa de entrega para um endereço usando HERE API.
    
    Args:
        store_id: ID da loja
        address: Endereço completo do cliente
    
    Returns:
        Dict com fee, distance_km, duration_minutes, is_valid, message
    """
    try:
        from apps.stores.models import Store
        from apps.stores.services.here_maps_service import here_maps_service
        from decimal import Decimal
        
        store = Store.objects.filter(id=store_id).first()
        if not store:
            return {
                'fee': None,
                'distance_km': None,
                'duration_minutes': None,
                'is_valid': False,
                'message': 'Loja não encontrada'
            }
        
        # Geocodifica endereço
        geocode_result = here_maps_service.geocode(address)
        
        if not geocode_result:
            return {
                'fee': float(store.default_delivery_fee or Decimal('5.00')),
                'distance_km': None,
                'duration_minutes': None,
                'is_valid': True,
                'message': 'Não foi possível calcular a distância. Taxa padrão aplicada.',
                'formatted_address': address
            }
        
        # Calcula rota
        store_lat = float(store.latitude) if store.latitude else -10.1849
        store_lng = float(store.longitude) if store.longitude else -48.3346
        
        route = here_maps_service.calculate_route(
            (store_lat, store_lng),
            (geocode_result['lat'], geocode_result['lng'])
        )
        
        if not route:
            return {
                'fee': float(store.default_delivery_fee or Decimal('5.00')),
                'distance_km': None,
                'duration_minutes': None,
                'is_valid': True,
                'message': 'Não foi possível calcular a rota. Taxa padrão aplicada.',
                'formatted_address': geocode_result['formatted_address']
            }
        
        # Calcula taxa baseada na distância
        distance_km = route['distance_km']
        
        # Regras de taxa
        if distance_km <= 3:
            fee = Decimal('5.00')
        elif distance_km <= 5:
            fee = Decimal('5.00') + (Decimal(str(distance_km)) - 3) * Decimal('1.50')
        else:
            fee = Decimal('8.00') + (Decimal(str(distance_km)) - 5) * Decimal('2.00')
        
        # Verifica limite máximo de distância (20km)
        max_distance = 20.0
        if distance_km > max_distance:
            return {
                'fee': None,
                'distance_km': distance_km,
                'duration_minutes': route['duration_minutes'],
                'is_valid': False,
                'message': f'Endereço fora da área de entrega (máx: {max_distance}km)',
                'formatted_address': geocode_result['formatted_address']
            }
        
        return {
            'fee': float(fee.quantize(Decimal('0.01'))),
            'distance_km': distance_km,
            'duration_minutes': route['duration_minutes'],
            'is_valid': True,
            'message': 'Endereço válido para entrega',
            'formatted_address': geocode_result['formatted_address'],
            'polyline': route.get('polyline', '')
        }
        
    except Exception as e:
        logger.error(f"Erro ao calcular taxa de entrega: {e}")
        return {
            'fee': None,
            'distance_km': None,
            'duration_minutes': None,
            'is_valid': False,
            'message': f'Erro ao calcular: {str(e)}'
        }


@tool
def create_order(session_id: str, payment_method: str, delivery_method: str = 'pickup') -> Dict[str, Any]:
    """
    Cria um pedido no sistema a partir do carrinho.
    
    Args:
        session_id: ID da sessão do cliente
        payment_method: Método de pagamento (pix, cash, card)
        delivery_method: Método de entrega (pickup, delivery)
    
    Returns:
        Dict com order_id, order_number, total, status
    """
    try:
        from apps.automation.models import CustomerSession
        from apps.stores.models import StoreOrder, StoreOrderItem
        from decimal import Decimal
        
        session = CustomerSession.objects.filter(id=session_id).first()
        if not session:
            return {'success': False, 'error': 'Sessão não encontrada'}
        
        cart_data = session.cart_data or {'items': []}
        items = cart_data.get('items', [])
        
        if not items:
            return {'success': False, 'error': 'Carrinho vazio'}
        
        # Calcula total
        subtotal = session.cart_total
        delivery_fee = session.delivery_fee or Decimal('0')
        total = subtotal + delivery_fee
        
        # Cria pedido
        order = StoreOrder.objects.create(
            store=session.company.store,
            customer_name=session.customer_name or 'Cliente',
            customer_phone=session.phone_number,
            status='confirmed' if payment_method in ['cash', 'card'] else 'pending',
            payment_status='pending',
            payment_method=payment_method,
            delivery_method=delivery_method,
            delivery_address={'address': session.delivery_address} if session.delivery_address else {},
            delivery_fee=delivery_fee,
            subtotal=subtotal,
            total=total
        )
        
        # Cria itens do pedido
        for item_data in items:
            StoreOrderItem.objects.create(
                order=order,
                product_id=item_data.get('product_id'),
                product_name=item_data.get('name', 'Produto'),
                quantity=item_data.get('quantity', 1),
                unit_price=Decimal(item_data.get('price', '0')),
                subtotal=Decimal(item_data.get('price', '0')) * item_data.get('quantity', 1),
                notes=item_data.get('notes', '')
            )
        
        # Atualiza sessão
        session.order_id = str(order.id)
        session.payment_method = payment_method
        session.status = 'order_placed'
        session.save()
        
        return {
            'success': True,
            'order_id': str(order.id),
            'order_number': order.order_number,
            'total': float(total),
            'status': order.status,
            'payment_method': payment_method,
            'delivery_method': delivery_method
        }
        
    except Exception as e:
        logger.error(f"Erro ao criar pedido: {e}")
        return {'success': False, 'error': str(e)}


@tool
def generate_pix(order_id: str) -> Dict[str, Any]:
    """
    Gera código PIX para um pedido via Mercado Pago.
    
    Args:
        order_id: ID do pedido (StoreOrder.id)
    
    Returns:
        Dict com pix_code, qr_code, expiration, payment_id
    """
    try:
        from apps.stores.models import StoreOrder, StorePayment, StorePaymentGateway
        from django.conf import settings
        import mercadopago
        
        order = StoreOrder.objects.filter(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Pedido não encontrado'}
        
        # Verifica se já existe PIX
        existing = StorePayment.objects.filter(
            order=order,
            payment_method='pix'
        ).order_by('-created_at').first()
        
        if existing and existing.pix_code:
            return {
                'success': True,
                'pix_code': existing.pix_code,
                'qr_code': existing.pix_qr_code,
                'payment_id': existing.payment_id,
                'expiration': existing.expires_at.isoformat() if existing.expires_at else None,
                'amount': float(existing.amount)
            }
        
        # Gera novo PIX
        access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
        if not access_token:
            return {'success': False, 'error': 'Mercado Pago não configurado'}
        
        sdk = mercadopago.SDK(access_token)
        
        payment_data = {
            "transaction_amount": float(order.total),
            "description": f"Pedido {order.order_number} - {order.store.name}",
            "payment_method_id": "pix",
            "payer": {
                "email": order.customer_email or "cliente@pastita.com.br",
                "first_name": order.customer_name or "Cliente",
            },
            "external_reference": order.order_number,
            "notification_url": f"{getattr(settings, 'BACKEND_URL', '')}/webhooks/v1/mercadopago",
        }
        
        payment_response = sdk.payment().create(payment_data)
        
        if payment_response["status"] == 201:
            payment_info = payment_response["response"]
            
            pix_code = payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
            pix_qr_code = payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code_base64", "")
            payment_id = payment_info.get("id", "")
            expiration = payment_info.get("date_of_expiration")
            
            # Salva no banco
            gateway = StorePaymentGateway.objects.filter(
                store=order.store,
                gateway_type='mercadopago'
            ).first()
            
            payment = StorePayment.objects.create(
                order=order,
                gateway=gateway,
                amount=order.total,
                payment_method='pix',
                payer_name=order.customer_name,
                payer_email=order.customer_email or "cliente@pastita.com.br",
                external_id=str(payment_id),
                pix_code=pix_code,
                pix_qr_code=pix_qr_code,
                gateway_response=payment_info,
                status='pending',
                expires_at=expiration
            )
            
            return {
                'success': True,
                'pix_code': pix_code,
                'qr_code': pix_qr_code,
                'payment_id': str(payment.id),
                'expiration': expiration,
                'amount': float(order.total)
            }
        else:
            return {'success': False, 'error': f"Erro Mercado Pago: {payment_response}"}
            
    except Exception as e:
        logger.error(f"Erro ao gerar PIX: {e}")
        return {'success': False, 'error': str(e)}


@tool
def check_order_status(order_number: str) -> str:
    """
    Verifica o status de um pedido pelo número.
    
    Args:
        order_number: Número do pedido (ex: PAS2502241234)
    
    Returns:
        Status formatado do pedido
    """
    try:
        from apps.stores.models import StoreOrder
        
        order = StoreOrder.objects.filter(order_number=order_number).first()
        
        if not order:
            return f"❌ Pedido *{order_number}* não encontrado.\n\nVerifique o número e tente novamente."
        
        status_map = {
            'pending': '⏳ *Pendente* - Aguardando confirmação',
            'confirmed': '✅ *Confirmado* - Pedido recebido',
            'preparing': '👨‍🍳 *Em Preparo* - Estamos preparando seu pedido',
            'ready': '📦 *Pronto* - Seu pedido está pronto!',
            'out_for_delivery': '🛵 *Saiu para Entrega* - Chegando em breve',
            'delivered': '✅ *Entregue* - Pedido entregue com sucesso',
            'cancelled': '❌ *Cancelado* - Pedido cancelado',
        }
        
        payment_map = {
            'pending': '⏳ Aguardando pagamento',
            'paid': '✅ Pago',
            'failed': '❌ Falhou',
            'refunded': '↩️ Reembolsado',
        }
        
        lines = [
            f"📦 *Pedido {order.order_number}*",
            f"",
            f"{status_map.get(order.status, order.status)}",
            f"💰 Pagamento: {payment_map.get(order.payment_status, order.payment_status)}",
            f"💵 Total: R$ {order.total:.2f}",
        ]
        
        if order.delivery_method == 'delivery':
            lines.append(f"🛵 Entrega")
        else:
            lines.append(f"🏪 Retirada na loja")
        
        if order.tracking_code:
            lines.append(f"\n📍 Rastreamento: {order.tracking_code}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Erro ao verificar status: {e}")
        return "❌ Erro ao verificar status do pedido."


@tool
def get_automessage_for_status(company_id: str, status: str) -> Optional[str]:
    """
    Busca mensagem automática configurada para um status específico.
    
    Args:
        company_id: ID da empresa (CompanyProfile.id)
        status: Status do pedido (confirmed, preparing, ready, etc.)
    
    Returns:
        Texto da mensagem ou None se não encontrada
    """
    try:
        from apps.automation.models import CompanyProfile, AutoMessage
        
        company = CompanyProfile.objects.filter(id=company_id).first()
        if not company:
            return None
        
        # Mapeia status para event_type
        event_map = {
            'confirmed': 'order_confirmed',
            'preparing': 'order_preparing',
            'ready': 'order_ready',
            'out_for_delivery': 'order_out_for_delivery',
            'delivered': 'order_delivered',
            'cancelled': 'order_cancelled',
        }
        
        event_type = event_map.get(status)
        if not event_type:
            return None
        
        auto_message = AutoMessage.objects.filter(
            company=company,
            event_type=event_type,
            is_active=True
        ).first()
        
        return auto_message.message_text if auto_message else None
        
    except Exception as e:
        logger.error(f"Erro ao buscar mensagem automática: {e}")
        return None


@tool
def send_whatsapp_message(account_id: str, to_number: str, message: str, message_type: str = 'text') -> Dict[str, Any]:
    """
    Envia mensagem via WhatsApp.
    
    Args:
        account_id: ID da conta WhatsApp
        to_number: Número do destinatário
        message: Conteúdo da mensagem
        message_type: Tipo da mensagem (text, buttons, list)
    
    Returns:
        Dict com success, message_id
    """
    try:
        from apps.whatsapp.services import MessageService
        
        service = MessageService()
        
        if message_type == 'text':
            result = service.send_text_message(
                account_id=account_id,
                to=to_number,
                text=message
            )
        else:
            # Para botões e listas, a mensagem deve ser processada pelo handler apropriado
            result = service.send_text_message(
                account_id=account_id,
                to=to_number,
                text=message
            )
        
        return {
            'success': True,
            'message_id': str(result.id) if result else None
        }
        
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return {'success': False, 'error': str(e)}


# Lista de todas as tools disponíveis
PASTITA_TOOLS = [
    get_menu,
    get_product_info,
    add_to_cart,
    remove_from_cart,
    view_cart,
    clear_cart,
    calculate_delivery_fee,
    create_order,
    generate_pix,
    check_order_status,
    get_automessage_for_status,
    send_whatsapp_message,
]
