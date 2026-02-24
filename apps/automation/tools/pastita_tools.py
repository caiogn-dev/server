"""
Pastita Tools - Tools for LangGraph orchestration.

This module provides all tools used by the LangGraph for WhatsApp bot automation.
All tools have complete error handling and are production-ready.
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from apps.stores.models import (
    Store, StoreProduct, StoreOrder, StoreOrderItem, StorePayment, StorePaymentGateway
)
from apps.automation.models import CustomerSession, CompanyProfile, AutoMessage
from apps.stores.services.here_maps_service import here_maps_service

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Exception raised by tools."""
    def __init__(self, message: str, code: str = "TOOL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


def get_menu(store_id: str) -> Dict[str, Any]:
    """
    Get formatted menu for a store.
    
    Args:
        store_id: UUID of the store
        
    Returns:
        Dict with menu data including categories and products
        
    Raises:
        ToolError: If store not found or error fetching menu
    """
    try:
        store = Store.objects.filter(id=store_id).first()
        if not store:
            raise ToolError("Loja não encontrada", "STORE_NOT_FOUND")
        
        # Get active products
        products = StoreProduct.objects.filter(
            store=store,
            status=StoreProduct.ProductStatus.ACTIVE
        ).select_related('category').order_by('category__sort_order', 'sort_order')
        
        # Group by category
        menu_data = {}
        for product in products:
            category_name = product.category.name if product.category else "Outros"
            if category_name not in menu_data:
                menu_data[category_name] = []
            
            menu_data[category_name].append({
                'id': str(product.id),
                'name': product.name,
                'description': product.short_description or product.description[:100] if product.description else "",
                'price': float(product.price),
                'sku': product.sku,
                'image_url': product.get_main_image_url() if hasattr(product, 'get_main_image_url') else None,
                'is_available': product.is_in_stock if hasattr(product, 'is_in_stock') else True,
            })
        
        return {
            'success': True,
            'store_name': store.name,
            'categories': [
                {
                    'name': cat_name,
                    'products': products_list
                }
                for cat_name, products_list in menu_data.items()
            ]
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error getting menu for store {store_id}: {e}", exc_info=True)
        raise ToolError("Erro ao buscar cardápio", "MENU_ERROR")


def add_to_cart(session_id: str, product_identifier: str, quantity: int = 1) -> Dict[str, Any]:
    """
    Add a product to the customer's cart.
    
    Args:
        session_id: Customer session ID
        product_identifier: Product ID, SKU, or name
        quantity: Quantity to add (default: 1)
        
    Returns:
        Dict with updated cart data
        
    Raises:
        ToolError: If session/product not found or error adding to cart
    """
    try:
        session = CustomerSession.objects.filter(session_id=session_id).first()
        if not session:
            raise ToolError("Sessão não encontrada", "SESSION_NOT_FOUND")
        
        # Try to find product by ID, SKU, or name
        product = None
        store = session.company.store if session.company and session.company.store else None
        
        if not store:
            raise ToolError("Loja não configurada para esta sessão", "STORE_NOT_CONFIGURED")
        
        # Try by ID first
        try:
            product = StoreProduct.objects.filter(
                id=product_identifier,
                store=store,
                status=StoreProduct.ProductStatus.ACTIVE
            ).first()
        except:
            pass
        
        # Try by SKU
        if not product:
            product = StoreProduct.objects.filter(
                store=store,
                sku=product_identifier,
                status=StoreProduct.ProductStatus.ACTIVE
            ).first()
        
        # Try by name (case-insensitive partial match)
        if not product:
            product = StoreProduct.objects.filter(
                store=store,
                name__icontains=product_identifier,
                status=StoreProduct.ProductStatus.ACTIVE
            ).first()
        
        if not product:
            raise ToolError(f"Produto '{product_identifier}' não encontrado", "PRODUCT_NOT_FOUND")
        
        # Check stock
        if hasattr(product, 'is_in_stock') and not product.is_in_stock:
            raise ToolError(f"Produto '{product.name}' está fora de estoque", "OUT_OF_STOCK")
        
        # Initialize cart if needed
        if not session.cart_data:
            session.cart_data = {'items': []}
        
        if 'items' not in session.cart_data:
            session.cart_data['items'] = []
        
        # Check if product already in cart
        existing_item = None
        for item in session.cart_data['items']:
            if item.get('product_id') == str(product.id):
                existing_item = item
                break
        
        if existing_item:
            existing_item['quantity'] += quantity
            existing_item['subtotal'] = float(product.price) * existing_item['quantity']
        else:
            session.cart_data['items'].append({
                'product_id': str(product.id),
                'name': product.name,
                'price': float(product.price),
                'quantity': quantity,
                'subtotal': float(product.price) * quantity,
                'sku': product.sku,
            })
        
        # Update cart totals
        session.cart_total = sum(item.get('subtotal', 0) for item in session.cart_data['items'])
        session.cart_items_count = sum(item.get('quantity', 0) for item in session.cart_data['items'])
        session.cart_updated_at = timezone.now()
        
        if not session.cart_created_at:
            session.cart_created_at = timezone.now()
        
        session.save(update_fields=['cart_data', 'cart_total', 'cart_items_count', 
                                    'cart_updated_at', 'cart_created_at'])
        
        return {
            'success': True,
            'message': f"{quantity}x {product.name} adicionado ao carrinho",
            'cart': {
                'items': session.cart_data['items'],
                'total': float(session.cart_total),
                'item_count': session.cart_items_count,
            }
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error adding to cart for session {session_id}: {e}", exc_info=True)
        raise ToolError("Erro ao adicionar ao carrinho", "CART_ADD_ERROR")


def remove_from_cart(session_id: str, item_index: int) -> Dict[str, Any]:
    """
    Remove an item from the cart by index.
    
    Args:
        session_id: Customer session ID
        item_index: Index of item to remove (0-based)
        
    Returns:
        Dict with updated cart data
        
    Raises:
        ToolError: If session not found, cart empty, or invalid index
    """
    try:
        session = CustomerSession.objects.filter(session_id=session_id).first()
        if not session:
            raise ToolError("Sessão não encontrada", "SESSION_NOT_FOUND")
        
        if not session.cart_data or not session.cart_data.get('items'):
            raise ToolError("Carrinho está vazio", "CART_EMPTY")
        
        items = session.cart_data['items']
        
        if item_index < 0 or item_index >= len(items):
            raise ToolError(f"Item {item_index + 1} não encontrado no carrinho", "INVALID_ITEM_INDEX")
        
        removed_item = items.pop(item_index)
        
        # Update totals
        session.cart_total = sum(item.get('subtotal', 0) for item in items)
        session.cart_items_count = sum(item.get('quantity', 0) for item in items)
        session.cart_updated_at = timezone.now()
        
        session.save(update_fields=['cart_data', 'cart_total', 'cart_items_count', 'cart_updated_at'])
        
        return {
            'success': True,
            'message': f"{removed_item.get('name', 'Item')} removido do carrinho",
            'cart': {
                'items': session.cart_data['items'],
                'total': float(session.cart_total),
                'item_count': session.cart_items_count,
            }
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error removing from cart for session {session_id}: {e}", exc_info=True)
        raise ToolError("Erro ao remover do carrinho", "CART_REMOVE_ERROR")


def view_cart(session_id: str) -> Dict[str, Any]:
    """
    View current cart contents.
    
    Args:
        session_id: Customer session ID
        
    Returns:
        Dict with cart data
        
    Raises:
        ToolError: If session not found
    """
    try:
        session = CustomerSession.objects.filter(session_id=session_id).first()
        if not session:
            raise ToolError("Sessão não encontrada", "SESSION_NOT_FOUND")
        
        if not session.cart_data or not session.cart_data.get('items'):
            return {
                'success': True,
                'cart': {
                    'items': [],
                    'total': 0.0,
                    'item_count': 0,
                },
                'is_empty': True,
                'message': "Seu carrinho está vazio"
            }
        
        return {
            'success': True,
            'cart': {
                'items': session.cart_data['items'],
                'total': float(session.cart_total),
                'item_count': session.cart_items_count,
            },
            'is_empty': False,
            'delivery_fee': float(session.delivery_fee) if session.delivery_fee else None,
            'final_total': float(session.cart_total + (session.delivery_fee or Decimal('0'))),
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error viewing cart for session {session_id}: {e}", exc_info=True)
        raise ToolError("Erro ao visualizar carrinho", "CART_VIEW_ERROR")


def clear_cart(session_id: str) -> Dict[str, Any]:
    """
    Clear all items from cart.
    
    Args:
        session_id: Customer session ID
        
    Returns:
        Dict with confirmation
        
    Raises:
        ToolError: If session not found
    """
    try:
        session = CustomerSession.objects.filter(session_id=session_id).first()
        if not session:
            raise ToolError("Sessão não encontrada", "SESSION_NOT_FOUND")
        
        session.cart_data = {'items': []}
        session.cart_total = Decimal('0')
        session.cart_items_count = 0
        session.cart_updated_at = timezone.now()
        
        session.save(update_fields=['cart_data', 'cart_total', 'cart_items_count', 'cart_updated_at'])
        
        return {
            'success': True,
            'message': "Carrinho limpo com sucesso",
            'cart': {
                'items': [],
                'total': 0.0,
                'item_count': 0,
            }
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error clearing cart for session {session_id}: {e}", exc_info=True)
        raise ToolError("Erro ao limpar carrinho", "CART_CLEAR_ERROR")


def calculate_delivery_fee(address: str, store_id: Optional[str] = None, 
                          session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate delivery fee for an address using HERE API.
    
    Args:
        address: Delivery address string
        store_id: Optional store ID (if session_id not provided)
        session_id: Optional session ID to get store from
        
    Returns:
        Dict with delivery fee calculation
        
    Raises:
        ToolError: If address invalid or store not found
    """
    try:
        store = None
        
        if session_id:
            session = CustomerSession.objects.filter(session_id=session_id).first()
            if session and session.company and session.company.store:
                store = session.company.store
        
        if not store and store_id:
            store = Store.objects.filter(id=store_id).first()
        
        if not store:
            raise ToolError("Loja não encontrada", "STORE_NOT_FOUND")
        
        # Get store coordinates
        store_lat = getattr(store, 'latitude', None)
        store_lng = getattr(store, 'longitude', None)
        
        if not store_lat or not store_lng:
            # Try to get from address_data
            if hasattr(store, 'address_data'):
                store_lat = store.address_data.get('lat')
                store_lng = store.address_data.get('lng')
        
        if not store_lat or not store_lng:
            raise ToolError("Localização da loja não configurada", "STORE_LOCATION_NOT_SET")
        
        # Geocode customer address
        geocode_result = here_maps_service.geocode(address)
        if not geocode_result:
            raise ToolError("Endereço não encontrado. Por favor, verifique e tente novamente.", "ADDRESS_NOT_FOUND")
        
        customer_lat = geocode_result['lat']
        customer_lng = geocode_result['lng']
        
        # Calculate delivery fee
        result = here_maps_service.calculate_delivery_fee(
            store=store,
            customer_lat=customer_lat,
            customer_lng=customer_lng
        )
        
        # Update session if provided
        if session_id:
            session = CustomerSession.objects.filter(session_id=session_id).first()
            if session:
                session.delivery_address = address
                session.delivery_fee = Decimal(str(result['fee'])) if result['fee'] else None
                session.save(update_fields=['delivery_address', 'delivery_fee'])
        
        return {
            'success': True,
            'address': geocode_result['formatted_address'],
            'distance_km': result['distance_km'],
            'duration_minutes': result['duration_minutes'],
            'fee': result['fee'],
            'is_within_area': result['is_within_area'],
            'message': result['message'],
            'zone': result.get('zone'),
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error calculating delivery fee: {e}", exc_info=True)
        raise ToolError("Erro ao calcular taxa de entrega", "DELIVERY_FEE_ERROR")


def create_order(session_id: str, payment_method: str, delivery_method: str,
                 address: Optional[str] = None) -> Dict[str, Any]:
    """
    Create an order from the current cart.
    
    Args:
        session_id: Customer session ID
        payment_method: 'pix', 'cash', 'card'
        delivery_method: 'delivery', 'pickup'
        address: Delivery address (required if delivery_method is 'delivery')
        
    Returns:
        Dict with order data
        
    Raises:
        ToolError: If cart empty, invalid data, or error creating order
    """
    try:
        session = CustomerSession.objects.filter(session_id=session_id).first()
        if not session:
            raise ToolError("Sessão não encontrada", "SESSION_NOT_FOUND")
        
        # Validate cart
        if not session.cart_data or not session.cart_data.get('items'):
            raise ToolError("Não é possível finalizar: carrinho está vazio", "CART_EMPTY")
        
        store = session.company.store if session.company and session.company.store else None
        if not store:
            raise ToolError("Loja não configurada", "STORE_NOT_CONFIGURED")
        
        # Validate delivery
        if delivery_method == 'delivery':
            if not address and not session.delivery_address:
                raise ToolError("Endereço de entrega é obrigatório", "ADDRESS_REQUIRED")
            if not address:
                address = session.delivery_address
            
            # Validate address is within delivery area
            fee_result = calculate_delivery_fee(address, session_id=session_id)
            if not fee_result['is_within_area']:
                raise ToolError(fee_result['message'], "OUTSIDE_DELIVERY_AREA")
        
        # Create order
        with transaction.atomic():
            order = StoreOrder.objects.create(
                store=store,
                customer_name=session.customer_name or "Cliente",
                customer_email=session.customer_email or "",
                customer_phone=session.phone_number,
                subtotal=session.cart_total,
                delivery_fee=session.delivery_fee or Decimal('0') if delivery_method == 'delivery' else Decimal('0'),
                total=session.cart_total + (session.delivery_fee or Decimal('0')) if delivery_method == 'delivery' else session.cart_total,
                delivery_method=delivery_method,
                delivery_address={'address': address} if address else {},
                payment_method=payment_method,
                status=StoreOrder.OrderStatus.PENDING,
                payment_status=StoreOrder.PaymentStatus.PENDING,
            )
            
            # Create order items
            for item in session.cart_data['items']:
                StoreOrderItem.objects.create(
                    order=order,
                    product_id=item.get('product_id'),
                    product_name=item.get('name', 'Produto'),
                    unit_price=Decimal(str(item.get('price', 0))),
                    quantity=item.get('quantity', 1),
                    subtotal=Decimal(str(item.get('subtotal', 0))),
                    sku=item.get('sku', ''),
                )
            
            # Update session
            session.order = order
            session.external_order_id = order.order_number
            session.delivery_method = delivery_method
            session.payment_method = payment_method
            if address:
                session.delivery_address = address
            session.status = CustomerSession.SessionStatus.ORDER_PLACED
            session.save(update_fields=['order', 'external_order_id', 'delivery_method', 
                                       'payment_method', 'delivery_address', 'status'])
        
        return {
            'success': True,
            'order_id': str(order.id),
            'order_number': order.order_number,
            'total': float(order.total),
            'delivery_method': delivery_method,
            'payment_method': payment_method,
            'message': f"Pedido #{order.order_number} criado com sucesso!"
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error creating order for session {session_id}: {e}", exc_info=True)
        raise ToolError("Erro ao criar pedido", "ORDER_CREATE_ERROR")


def generate_pix(order_id: str) -> Dict[str, Any]:
    """
    Generate PIX payment for an order via Mercado Pago.
    
    Args:
        order_id: Order UUID
        
    Returns:
        Dict with PIX data (QR code, copy-paste code)
        
    Raises:
        ToolError: If order not found or error generating PIX
    """
    try:
        order = StoreOrder.objects.filter(id=order_id).first()
        if not order:
            raise ToolError("Pedido não encontrado", "ORDER_NOT_FOUND")
        
        # Check if PIX already generated
        if order.pix_code and order.pix_qr_code:
            return {
                'success': True,
                'pix_code': order.pix_code,
                'qr_code': order.pix_qr_code,
                'ticket_url': order.pix_ticket_url,
                'amount': float(order.total),
                'message': "PIX já gerado para este pedido",
            }
        
        # Get store's Mercado Pago gateway
        gateway = order.store.payment_gateways.filter(
            gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
            is_enabled=True
        ).first()
        
        if not gateway:
            raise ToolError("Gateway de pagamento não configurado", "GATEWAY_NOT_CONFIGURED")
        
        # Import Mercado Pago SDK
        try:
            import mercadopago
        except ImportError:
            raise ToolError("SDK do Mercado Pago não instalado", "MP_SDK_NOT_FOUND")
        
        sdk = mercadopago.SDK(gateway.access_token)
        
        # Create payment preference
        preference_data = {
            "items": [
                {
                    "title": f"Pedido #{order.order_number}",
                    "quantity": 1,
                    "unit_price": float(order.total),
                    "currency_id": "BRL",
                }
            ],
            "payer": {
                "name": order.customer_name,
                "email": order.customer_email or f"cliente{order.order_number}@pastita.com",
                "phone": {
                    "number": order.customer_phone,
                }
            },
            "external_reference": order.order_number,
            "notification_url": f"{settings.SITE_URL}/webhooks/mercadopago/" if hasattr(settings, 'SITE_URL') else None,
        }
        
        preference_response = sdk.preference().create(preference_data)
        
        if preference_response["status"] != 201:
            raise ToolError("Erro ao criar preferência de pagamento", "PREFERENCE_ERROR")
        
        preference = preference_response["response"]
        
        # Get PIX payment method
        payment_methods = sdk.payment().create({
            "transaction_amount": float(order.total),
            "description": f"Pedido #{order.order_number}",
            "payment_method_id": "pix",
            "payer": {
                "email": order.customer_email or f"cliente{order.order_number}@pastita.com",
                "first_name": order.customer_name.split()[0] if order.customer_name else "Cliente",
                "last_name": " ".join(order.customer_name.split()[1:]) if order.customer_name and len(order.customer_name.split()) > 1 else "",
            }
        })
        
        # Store PIX data
        if payment_methods["status"] == 201:
            payment_data = payment_methods["response"]
            
            order.pix_code = payment_data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code")
            order.pix_qr_code = payment_data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code_base64")
            order.pix_ticket_url = payment_data.get("point_of_interaction", {}).get("transaction_data", {}).get("ticket_url")
            order.payment_id = str(payment_data.get("id"))
            order.payment_preference_id = preference["id"]
            order.save(update_fields=['pix_code', 'pix_qr_code', 'pix_ticket_url', 
                                      'payment_id', 'payment_preference_id'])
            
            # Create StorePayment record
            StorePayment.objects.create(
                order=order,
                gateway=gateway,
                amount=order.total,
                payment_method=StorePayment.PaymentMethod.PIX,
                status=StorePayment.PaymentStatus.PENDING,
                external_id=str(payment_data.get("id")),
                external_reference=order.order_number,
                payer_email=order.customer_email,
                payer_name=order.customer_name,
                qr_code=order.pix_code,
                qr_code_base64=order.pix_qr_code,
                ticket_url=order.pix_ticket_url,
                expires_at=timezone.now() + timezone.timedelta(minutes=30),
            )
            
            return {
                'success': True,
                'pix_code': order.pix_code,
                'qr_code': order.pix_qr_code,
                'ticket_url': order.pix_ticket_url,
                'amount': float(order.total),
                'expires_in_minutes': 30,
                'message': "PIX gerado com sucesso! Escaneie o QR code ou copie o código."
            }
        else:
            raise ToolError("Erro ao gerar PIX", "PIX_GENERATION_ERROR")
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error generating PIX for order {order_id}: {e}", exc_info=True)
        raise ToolError("Erro ao gerar PIX", "PIX_ERROR")


def check_order_status(order_number: str) -> Dict[str, Any]:
    """
    Check the status of an order.
    
    Args:
        order_number: Order number (e.g., ABC2402011234)
        
    Returns:
        Dict with order status information
        
    Raises:
        ToolError: If order not found
    """
    try:
        order = StoreOrder.objects.filter(order_number=order_number).first()
        if not order:
            raise ToolError(f"Pedido #{order_number} não encontrado", "ORDER_NOT_FOUND")
        
        # Get order items
        items = []
        for item in order.items.all():
            items.append({
                'name': item.product_name,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'subtotal': float(item.subtotal),
            })
        
        status_display = dict(StoreOrder.OrderStatus.choices).get(order.status, order.status)
        payment_status_display = dict(StoreOrder.PaymentStatus.choices).get(order.payment_status, order.payment_status)
        
        return {
            'success': True,
            'order_number': order.order_number,
            'status': order.status,
            'status_display': status_display,
            'payment_status': order.payment_status,
            'payment_status_display': payment_status_display,
            'total': float(order.total),
            'items': items,
            'delivery_method': order.delivery_method,
            'delivery_address': order.delivery_address,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'paid_at': order.paid_at.isoformat() if order.paid_at else None,
            'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
            'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            'tracking_code': order.tracking_code,
            'tracking_url': order.tracking_url,
        }
        
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Error checking order status for {order_number}: {e}", exc_info=True)
        raise ToolError("Erro ao verificar status do pedido", "STATUS_CHECK_ERROR")


def get_automessage(company_id: str, trigger: str, context: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """
    Get an automated message for a specific trigger.
    
    Args:
        company_id: Company profile ID
        trigger: Event type trigger (e.g., 'welcome', 'order_confirmed')
        context: Optional context dict for variable substitution
        
    Returns:
        Dict with message data or None if not found
    """
    try:
        company = CompanyProfile.objects.filter(id=company_id).first()
        if not company:
            return None
        
        automessage = AutoMessage.objects.filter(
            company=company,
            event_type=trigger,
            is_active=True
        ).order_by('priority').first()
        
        if not automessage:
            return None
        
        # Render message with context
        message_text = automessage.message_text
        if context:
            message_text = automessage.render_message(context)
        
        return {
            'success': True,
            'message_text': message_text,
            'media_url': automessage.media_url,
            'media_type': automessage.media_type,
            'buttons': automessage.buttons,
            'delay_seconds': automessage.delay_seconds,
        }
        
    except Exception as e:
        logger.error(f"Error getting automessage for company {company_id}, trigger {trigger}: {e}", exc_info=True)
        return None


# Tool registry for LangGraph
TOOL_REGISTRY = {
    'get_menu': get_menu,
    'add_to_cart': add_to_cart,
    'remove_from_cart': remove_from_cart,
    'view_cart': view_cart,
    'clear_cart': clear_cart,
    'calculate_delivery_fee': calculate_delivery_fee,
    'create_order': create_order,
    'generate_pix': generate_pix,
    'check_order_status': check_order_status,
    'get_automessage': get_automessage,
}


def execute_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Execute a tool by name with given arguments.
    
    Args:
        tool_name: Name of the tool to execute
        **kwargs: Arguments to pass to the tool
        
    Returns:
        Dict with tool result
    """
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        return {
            'success': False,
            'error': f"Tool '{tool_name}' não encontrada",
            'error_code': "TOOL_NOT_FOUND"
        }
    
    try:
        return tool(**kwargs)
    except ToolError as e:
        return {
            'success': False,
            'error': e.message,
            'error_code': e.code
        }
    except Exception as e:
        logger.error(f"Unexpected error executing tool {tool_name}: {e}", exc_info=True)
        return {
            'success': False,
            'error': "Erro inesperado",
            'error_code': "UNEXPECTED_ERROR"
        }
