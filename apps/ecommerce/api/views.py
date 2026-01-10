"""
E-commerce API views - compatible with Pastita frontend.
"""
import logging
import uuid
import time
from functools import wraps
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from ..models import Product, Cart, CartItem, Checkout, Wishlist, Coupon, DeliveryZone, StoreLocation
from apps.notifications.services import NotificationService
from apps.orders.repositories import OrderRepository
from apps.orders.models import Order
from apps.payments.services import PaymentService
from apps.payments.models import Payment, PaymentGateway
from apps.whatsapp.models import WhatsAppAccount
from .serializers import (
    ProductSerializer,
    CartSerializer,
    CartItemSerializer,
    AddToCartSerializer,
    UpdateCartItemSerializer,
    RemoveFromCartSerializer,
    CheckoutSerializer,
    CreateCheckoutSerializer,
    WishlistSerializer,
    CouponSerializer,
    ValidateCouponSerializer,
    DeliveryFeeSerializer,
    DeliveryZoneSerializer,
    StoreLocationSerializer,
)
from ..services import MercadoPagoService
from ..services.delivery_distance_service import DeliveryDistanceService

logger = logging.getLogger(__name__)
User = get_user_model()


def rate_limit(key_prefix: str, max_requests: int = 5, window_seconds: int = 60):
    """
    Rate limiting decorator for API views.
    
    Args:
        key_prefix: Prefix for the cache key
        max_requests: Maximum number of requests allowed in the window
        window_seconds: Time window in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            # Build rate limit key based on user or IP
            if request.user.is_authenticated:
                identifier = f"user_{request.user.id}"
            else:
                identifier = f"ip_{request.META.get('REMOTE_ADDR', 'unknown')}"
            
            cache_key = f"rate_limit:{key_prefix}:{identifier}"
            
            # Get current request count and timestamp
            rate_data = cache.get(cache_key)
            current_time = time.time()
            
            if rate_data is None:
                # First request in window
                rate_data = {'count': 1, 'window_start': current_time}
                cache.set(cache_key, rate_data, window_seconds)
            else:
                # Check if window has expired
                if current_time - rate_data['window_start'] > window_seconds:
                    # Reset window
                    rate_data = {'count': 1, 'window_start': current_time}
                    cache.set(cache_key, rate_data, window_seconds)
                else:
                    # Increment count
                    rate_data['count'] += 1
                    
                    if rate_data['count'] > max_requests:
                        remaining_time = int(window_seconds - (current_time - rate_data['window_start']))
                        logger.warning(
                            f"Rate limit exceeded for {identifier} on {key_prefix}. "
                            f"Count: {rate_data['count']}, Max: {max_requests}"
                        )
                        return Response(
                            {
                                'error': 'Rate limit exceeded',
                                'message': f'Too many requests. Please try again in {remaining_time} seconds.',
                                'retry_after': remaining_time
                            },
                            status=status.HTTP_429_TOO_MANY_REQUESTS,
                            headers={'Retry-After': str(remaining_time)}
                        )
                    
                    cache.set(cache_key, rate_data, window_seconds)
            
            return func(self, request, *args, **kwargs)
        return wrapper
    return decorator


class ProductViewSet(viewsets.ModelViewSet):
    """
    Product catalog API.
    
    list: GET /api/v1/ecommerce/products/
    retrieve: GET /api/v1/ecommerce/products/{id}/
    search: GET /api/v1/ecommerce/products/?search=term
    categories: GET /api/v1/ecommerce/products/categories/
    """
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['name', 'price', 'created_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all unique categories"""
        categories = Product.objects.filter(is_active=True).values_list(
            'category', flat=True
        ).distinct().exclude(category__isnull=True).exclude(category='')
        return Response(list(categories))

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search products by query"""
        query = request.query_params.get('q', '')
        if not query:
            return Response([])
        
        products = self.queryset.filter(
            name__icontains=query
        ) | self.queryset.filter(
            description__icontains=query
        )
        serializer = self.get_serializer(products[:20], many=True)
        return Response(serializer.data)


class CartViewSet(viewsets.GenericViewSet):
    """
    Shopping cart API.
    
    list: GET /api/v1/ecommerce/cart/list/
    add_item: POST /api/v1/ecommerce/cart/add_item/
    update_item: POST /api/v1/ecommerce/cart/update_item/
    remove_item: POST /api/v1/ecommerce/cart/remove_item/
    clear: POST /api/v1/ecommerce/cart/clear/
    """
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_cart(self, request):
        """Get or create cart for current user"""
        cart, created = Cart.objects.get_or_create(user=request.user)
        return cart

    @action(detail=False, methods=['get'], url_path='list')
    def get_cart_list(self, request):
        """Get current user's cart"""
        cart = self.get_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart"""
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']
        
        product = get_object_or_404(Product, id=product_id, is_active=True)
        cart = self.get_cart(request)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )
        
        if not created:
            cart_item.quantity += quantity
            cart_item.save()
        
        # Trigger webhook for cart update
        self._notify_cart_update(cart, 'cart_updated')
        
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['post'])
    def update_item(self, request):
        """Update item quantity in cart"""
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        item_id = serializer.validated_data.get('item_id')
        product_id = serializer.validated_data.get('product_id')
        quantity = serializer.validated_data['quantity']
        
        cart = self.get_cart(request)
        if item_id:
            cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        else:
            cart_item = get_object_or_404(CartItem, product_id=product_id, cart=cart)
        
        if quantity == 0:
            cart_item.delete()
        else:
            cart_item.quantity = quantity
            cart_item.save()
        
        self._notify_cart_update(cart, 'cart_updated')
        
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        """Remove item from cart"""
        serializer = RemoveFromCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        item_id = serializer.validated_data.get('item_id')
        product_id = serializer.validated_data.get('product_id')
        cart = self.get_cart(request)
        
        if item_id:
            CartItem.objects.filter(id=item_id, cart=cart).delete()
        else:
            CartItem.objects.filter(product_id=product_id, cart=cart).delete()
        
        self._notify_cart_update(cart, 'cart_updated')
        
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['post'])
    def clear(self, request):
        """Clear all items from cart"""
        cart = self.get_cart(request)
        cart.items.all().delete()
        
        return Response(CartSerializer(cart).data)

    def _notify_cart_update(self, cart, event_type):
        """Send cart update to automation webhook"""
        try:
            from apps.automation.services import AutomationService
            
            if cart.phone_number or (cart.user and hasattr(cart.user, 'phone')):
                phone = cart.phone_number or getattr(cart.user, 'phone', None)
                if phone:
                    # This will be handled by the automation system
                    logger.info(f"Cart {event_type} for phone {phone}")
        except Exception as e:
            logger.warning(f"Could not notify cart update: {e}")


class CheckoutViewSet(viewsets.GenericViewSet):
    """
    Checkout API with Mercado Pago integration.
    
    create_checkout: POST /api/v1/ecommerce/checkout/create_checkout/
    list: GET /api/v1/ecommerce/checkout/list/
    details: GET /api/v1/ecommerce/checkout/details/?token=xxx
    """
    serializer_class = CheckoutSerializer
    permission_classes = [IsAuthenticated]

    def _get_admin_users(self):
        """Return active superadmin users."""
        return User.objects.filter(is_superuser=True, is_active=True)

    def _notify_admins(self, title: str, message: str, notification_type: str, data: dict, related_type: str, related_id: str):
        """Send notification to all superadmins."""
        service = NotificationService()
        for admin in self._get_admin_users():
            service.create_notification(
                title=title,
                message=message,
                notification_type=notification_type,
                user=admin,
                data=data,
                related_object_type=related_type,
                related_object_id=related_id,
            )

    def _get_default_account(self) -> WhatsAppAccount:
        """Resolve or create the default account for ecommerce orders."""
        account_id = getattr(settings, 'ECOMMERCE_DEFAULT_ACCOUNT_ID', '').strip()
        if account_id:
            account = WhatsAppAccount.objects.filter(id=account_id, is_active=True).first()
            if account:
                return account

        account = WhatsAppAccount.objects.filter(
            metadata__ecommerce_system=True,
            is_active=True
        ).first()
        if account:
            return account

        account = WhatsAppAccount.objects.filter(is_active=True).order_by('created_at').first()
        if account:
            return account

        owner = self._get_admin_users().order_by('id').first()
        phone_number_id = f"ecommerce-{uuid.uuid4().hex[:12]}"
        waba_id = f"ecommerce-{uuid.uuid4().hex[:12]}"

        account = WhatsAppAccount(
            name='Pastita Store (Sistema)',
            phone_number_id=phone_number_id,
            waba_id=waba_id,
            phone_number='5500000000000',
            display_phone_number='',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
            owner=owner,
            metadata={'ecommerce_system': True},
        )
        account.access_token = 'ecommerce-placeholder'
        account.save()
        return account

    def _resolve_payment_method(self, request) -> str:
        """Map frontend payment payload to payment method."""
        payment_payload = request.data.get('payment') or {}
        method = payment_payload.get('method') or payment_payload.get('payment_method_id')
        if not method:
            return ''
        method = str(method).lower()
        if method in ['pix']:
            return Payment.PaymentMethod.PIX
        if method in ['boleto', 'bolbradesco']:
            return Payment.PaymentMethod.BOLETO
        if method in ['cash', 'dinheiro', 'cash_on_delivery']:
            return Payment.PaymentMethod.CASH
        if method in ['credit_card', 'card']:
            return Payment.PaymentMethod.CREDIT_CARD
        if method in ['debit_card']:
            return Payment.PaymentMethod.DEBIT_CARD
        return Payment.PaymentMethod.OTHER

    def _get_gateway_for_payment(self, account: WhatsAppAccount, payment_method: str):
        """Return matching gateway if available."""
        gateway_type = None
        if payment_method == Payment.PaymentMethod.PIX:
            gateway_type = PaymentGateway.GatewayType.PIX
        elif payment_method in [Payment.PaymentMethod.CREDIT_CARD, Payment.PaymentMethod.DEBIT_CARD]:
            gateway_type = PaymentGateway.GatewayType.MERCADOPAGO
        elif payment_method == Payment.PaymentMethod.BOLETO:
            gateway_type = PaymentGateway.GatewayType.MERCADOPAGO

        if not gateway_type:
            return None

        return PaymentGateway.objects.filter(
            gateway_type=gateway_type,
            is_enabled=True,
            is_active=True
        ).first()

    def _create_order_from_cart(self, cart: Cart, data: dict, request) -> Order:
        """Create an Order from the current cart."""
        account = self._get_default_account()
        order_repo = OrderRepository()

        shipping_address = {
            'address': data.get('shipping_address', ''),
            'city': data.get('shipping_city', ''),
            'state': data.get('shipping_state', ''),
            'zip_code': data.get('shipping_zip_code', ''),
            'method': request.data.get('shipping_method', ''),
        }

        order_items = []
        for item in cart.items.select_related('product').all():
            order_items.append({
                'product_id': str(item.product.id),
                'product_name': item.product.name,
                'product_sku': item.product.sku or '',
                'quantity': item.quantity,
                'unit_price': float(item.product.price),
                'total_price': float(item.product.price) * item.quantity,
                'metadata': {'source': 'ecommerce'},
            })

        metadata = {
            'source': 'ecommerce',
            'checkout_session': request.data.get('session_id', ''),
            'shipping_method': request.data.get('shipping_method', ''),
            'coupon_code': request.data.get('coupon_code', ''),
        }

        order = order_repo.create(
            account=account,
            customer_phone=data['customer_phone'],
            customer_name=data.get('customer_name', ''),
            customer_email=data.get('customer_email', ''),
            status=Order.OrderStatus.AWAITING_PAYMENT,
            subtotal=cart.get_total(),
            total=cart.get_total(),
            shipping_address=shipping_address,
            billing_address={},
            metadata=metadata,
            items=order_items,
        )

        return order

    def _create_payment_for_order(self, order: Order, checkout: Checkout, request):
        """Create a Payment record for the order."""
        payment_service = PaymentService()
        payment_method = self._resolve_payment_method(request)
        gateway = self._get_gateway_for_payment(order.account, payment_method)

        payment = payment_service.create_payment(
            order_id=str(order.id),
            amount=float(checkout.total_amount),
            gateway_id=str(gateway.id) if gateway else None,
            payment_method=payment_method,
            payer_email=checkout.customer_email,
            payer_name=checkout.customer_name,
            metadata={
                'source': 'ecommerce',
                'checkout_id': str(checkout.id),
                'session_token': checkout.session_token,
                'shipping_method': request.data.get('shipping_method', ''),
            },
        )

        if checkout.payment_link:
            payment.payment_url = checkout.payment_link
            payment.save(update_fields=['payment_url'])

        return payment

    @action(detail=False, methods=['post'])
    @rate_limit(key_prefix='checkout', max_requests=5, window_seconds=60)
    def create_checkout(self, request):
        """Create checkout from cart and generate Mercado Pago payment"""
        serializer = CreateCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        cart = Cart.objects.filter(user=request.user).first()
        if not cart or cart.get_item_count() == 0:
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        total_amount = cart.get_total()
        session_token = str(uuid.uuid4())
        
        # Get payment info from request
        payment_payload = request.data.get('payment') or {}
        payment_method = payment_payload.get('method', 'pix').lower()
        
        # Get CPF from request (needed for PIX/Boleto)
        # Try to get from profile or request
        customer_cpf = request.data.get('cpf', '')
        if not customer_cpf and hasattr(request.user, 'profile'):
            customer_cpf = getattr(request.user.profile, 'cpf', '') or ''
        
        payment_result = None
        payment_error = None
        
        with transaction.atomic():
            # Create checkout
            checkout = Checkout.objects.create(
                cart=cart,
                user=request.user,
                total_amount=total_amount,
                session_token=session_token,
                customer_name=data['customer_name'],
                customer_email=data['customer_email'],
                customer_phone=data['customer_phone'],
                shipping_address=data.get('shipping_address', ''),
                shipping_city=data.get('shipping_city', ''),
                shipping_state=data.get('shipping_state', ''),
                shipping_zip_code=data.get('shipping_zip_code', ''),
                shipping_method=data.get('shipping_method', 'delivery'),
                scheduled_date=data.get('scheduled_date'),
                scheduled_time_slot=data.get('scheduled_time_slot', ''),
            )

            # Create order for dashboard tracking
            order = self._create_order_from_cart(cart, data, request)
            order.metadata = {**(order.metadata or {}), 'checkout_id': str(checkout.id)}
            order.save(update_fields=['metadata'])
            checkout.order = order
            checkout.save(update_fields=['order'])
            
            # Update cart with phone number for automation
            cart.phone_number = data['customer_phone']
            cart.save(update_fields=['phone_number'])
            
            # Create Mercado Pago payment based on method
            mp_service = MercadoPagoService()
            if mp_service.is_configured():
                if payment_method == 'pix':
                    # Create direct PIX payment with QR code
                    result = mp_service.create_pix_payment(
                        checkout_id=str(checkout.id),
                        amount=float(total_amount),
                        customer_email=data['customer_email'],
                        customer_name=data['customer_name'],
                        customer_cpf=customer_cpf,
                        description=f'Pedido Pastita #{order.order_number}',
                        external_reference=order.order_number,
                    )
                    
                    if result.get('success'):
                        checkout.mercado_pago_payment_id = str(result.get('payment_id'))
                        checkout.pix_code = result.get('qr_code')
                        checkout.pix_qr_code = result.get('qr_code_base64')
                        checkout.payment_link = result.get('ticket_url') or checkout.payment_link
                        checkout.payment_status = 'processing'
                        checkout.save(update_fields=[
                            'mercado_pago_payment_id', 'pix_code', 'pix_qr_code', 'payment_link', 'payment_status'
                        ])
                        payment_result = result
                    else:
                        payment_error = result.get('error', 'Failed to create PIX payment')
                        logger.error(f"Failed to create PIX payment: {result}")
                
                elif payment_method in ['boleto', 'bolbradesco']:
                    # Create Boleto payment
                    result = mp_service.create_boleto_payment(
                        checkout_id=str(checkout.id),
                        amount=float(total_amount),
                        customer_email=data['customer_email'],
                        customer_name=data['customer_name'],
                        customer_cpf=customer_cpf,
                        description=f'Pedido Pastita #{order.order_number}',
                        external_reference=order.order_number,
                    )
                    
                    if result.get('success'):
                        checkout.mercado_pago_payment_id = str(result.get('payment_id'))
                        checkout.payment_link = result.get('ticket_url')
                        checkout.payment_status = 'processing'
                        checkout.save(update_fields=[
                            'mercado_pago_payment_id', 'payment_link', 'payment_status'
                        ])
                        payment_result = result
                    else:
                        payment_error = result.get('error', 'Failed to create Boleto payment')
                        logger.error(f"Failed to create Boleto payment: {result}")
                
                elif payment_method in ['cash', 'dinheiro', 'cash_on_delivery']:
                    # Cash on delivery - no online payment needed
                    checkout.payment_status = 'pending'
                    checkout.save(update_fields=['payment_status'])
                    
                    # Update order to awaiting payment (will be paid on delivery)
                    order.status = Order.Status.AWAITING_PAYMENT
                    order.notes = (order.notes or '') + '\n[Pagamento em dinheiro na entrega]'
                    order.save(update_fields=['status', 'notes'])
                    
                    payment_result = {
                        'success': True,
                        'status': 'pending',
                        'payment_method': 'cash',
                        'message': 'Pagamento será realizado na entrega'
                    }
                
                elif payment_method in ['card', 'credit_card', 'debit_card']:
                    # Create card payment using token from frontend
                    token = payment_payload.get('token')
                    card_payment_method_id = payment_payload.get('payment_method_id')
                    installments = payment_payload.get('installments', 1)
                    issuer_id = payment_payload.get('issuer_id')
                    
                    if not token or not card_payment_method_id:
                        payment_error = 'Token and payment_method_id are required for card payments'
                    else:
                        result = mp_service.create_card_payment(
                            checkout_id=str(checkout.id),
                            amount=float(total_amount),
                            token=token,
                            payment_method_id=card_payment_method_id,
                            installments=installments,
                            customer_email=data['customer_email'],
                            customer_name=data['customer_name'],
                            customer_cpf=customer_cpf,
                            issuer_id=issuer_id,
                            description=f'Pedido Pastita #{order.order_number}',
                            external_reference=order.order_number,
                        )
                        
                        if result.get('success'):
                            checkout.mercado_pago_payment_id = str(result.get('payment_id'))
                            payment_status = result.get('status')
                            if payment_status == 'approved':
                                checkout.payment_status = 'completed'
                            elif payment_status in ['rejected', 'cancelled']:
                                checkout.payment_status = 'failed'
                            else:
                                checkout.payment_status = 'processing'
                            checkout.save(update_fields=['mercado_pago_payment_id', 'payment_status'])
                            payment_result = result
                        else:
                            payment_error = result.get('error', 'Failed to create card payment')
                            logger.error(f"Failed to create card payment: {result}")
                
                else:
                    # Fallback: Create preference for redirect-based payment
                    items = [
                        {
                            'name': item.product.name,
                            'quantity': item.quantity,
                            'unit_price': float(item.product.price),
                        }
                        for item in cart.items.select_related('product').all()
                    ]
                    
                    result = mp_service.create_preference(
                        checkout_id=str(checkout.id),
                        items=items,
                        total_amount=total_amount,
                        customer_name=data['customer_name'],
                        customer_email=data['customer_email'],
                        customer_phone=data['customer_phone'],
                        external_reference=order.order_number,
                    )
                    
                    if result.get('success'):
                        checkout.mercado_pago_preference_id = result.get('preference_id')
                        checkout.payment_link = result.get('init_point')
                        checkout.save(update_fields=[
                            'mercado_pago_preference_id', 'payment_link'
                        ])
                        payment_result = {
                            'init_point': result.get('init_point'),
                            'sandbox_init_point': result.get('sandbox_init_point'),
                        }
                    else:
                        payment_error = result.get('error', 'Failed to create payment preference')
                        logger.error(f"Failed to create MP preference: {result}")
            
            # Create payment record for dashboard tracking
            payment = self._create_payment_for_order(order, checkout, request)

            # Notify automation system
            self._notify_checkout_created(checkout, cart)

            transaction.on_commit(lambda: self._notify_admins(
                title='Novo pedido criado',
                message=f"Pedido #{order.order_number} aguardando pagamento.",
                notification_type='order',
                data={
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'checkout_id': str(checkout.id),
                    'total': float(order.total),
                },
                related_type='order',
                related_id=str(order.id),
            ))
        
        # Build response with payment data
        response_data = CheckoutSerializer(checkout).data
        response_data['order_number'] = order.order_number
        
        if payment_result:
            response_data['payment'] = payment_result
        if payment_error:
            response_data['payment_error'] = payment_error
        
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='list')
    def get_checkout_list(self, request):
        """List user's checkouts"""
        checkouts = Checkout.objects.filter(user=request.user).order_by('-created_at')
        serializer = CheckoutSerializer(checkouts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def details(self, request):
        """Get checkout by session token"""
        token = request.query_params.get('token')
        if not token:
            return Response(
                {'error': 'Token required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        checkout = get_object_or_404(Checkout, session_token=token)
        return Response(CheckoutSerializer(checkout).data)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def status(self, request):
        """
        Get checkout/order status by order_number.
        Public endpoint - allows checking status without authentication.
        
        GET /api/v1/ecommerce/checkout/status/?order_number=xxx
        """
        order_number = request.query_params.get('order_number')
        if not order_number:
            return Response(
                {'error': 'order_number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to find checkout by order_number (which maps to order.order_number or session_token prefix)
        checkout = None
        
        # First try to find by order.order_number
        checkout = Checkout.objects.filter(
            order__order_number=order_number
        ).select_related('order', 'cart').first()
        
        # If not found, try by session_token prefix (legacy support)
        if not checkout:
            checkout = Checkout.objects.filter(
                session_token__istartswith=order_number
            ).select_related('order', 'cart').first()
        
        if not checkout:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Build response with order details
        response_data = {
            'order_number': checkout.order.order_number if checkout.order else checkout.session_token[:8].upper(),
            'payment_status': checkout.payment_status,
            'total_amount': float(checkout.total_amount),
            'customer_name': checkout.customer_name,
            'customer_email': checkout.customer_email,
            'shipping_address': checkout.shipping_address,
            'shipping_city': checkout.shipping_city,
            'shipping_state': checkout.shipping_state,
            'shipping_zip_code': checkout.shipping_zip_code,
            'created_at': checkout.created_at.isoformat(),
            'completed_at': checkout.completed_at.isoformat() if checkout.completed_at else None,
        }
        
        # Include order details if available
        if checkout.order:
            response_data['order'] = {
                'id': str(checkout.order.id),
                'order_number': checkout.order.order_number,
                'status': checkout.order.status,
                'total': float(checkout.order.total),
                'subtotal': float(checkout.order.subtotal),
            }
        
        # Include cart items if available
        if checkout.cart:
            items = []
            for cart_item in checkout.cart.items.select_related('product').all():
                items.append({
                    'id': str(cart_item.id),
                    'product_id': str(cart_item.product.id),
                    'product_name': cart_item.product.name,
                    'product_image': cart_item.product.get_image_url(),
                    'quantity': cart_item.quantity,
                    'price': float(cart_item.product.price),
                    'subtotal': float(cart_item.get_subtotal()),
                })
            response_data['items'] = items
        
        # Include payment data if available (PIX QR code, etc.)
        payment_data = {}
        if checkout.pix_code:
            payment_data['qr_code'] = checkout.pix_code
        if checkout.pix_qr_code:
            payment_data['qr_code_base64'] = checkout.pix_qr_code
        if checkout.payment_link:
            payment_data['payment_link'] = checkout.payment_link
        if checkout.mercado_pago_payment_id:
            payment_data['payment_id'] = checkout.mercado_pago_payment_id
        
        # Try to get payment details from Mercado Pago if we have a payment ID
        if checkout.mercado_pago_payment_id and not payment_data.get('qr_code'):
            try:
                mp_service = MercadoPagoService()
                if mp_service.is_configured():
                    mp_result = mp_service.get_payment(checkout.mercado_pago_payment_id)
                    if mp_result.get('success'):
                        mp_payment = mp_result.get('payment', {})
                        payment_data['status'] = mp_payment.get('status')
                        payment_data['status_detail'] = mp_payment.get('status_detail')
                        payment_data['payment_method_id'] = mp_payment.get('payment_method_id')
                        payment_data['payment_type_id'] = mp_payment.get('payment_type_id')
                        payment_data['transaction_amount'] = mp_payment.get('transaction_amount')
                        
                        # Extract PIX data if available
                        poi = mp_payment.get('point_of_interaction', {})
                        transaction_data = poi.get('transaction_data', {})
                        if transaction_data.get('qr_code'):
                            payment_data['qr_code'] = transaction_data.get('qr_code')
                        if transaction_data.get('qr_code_base64'):
                            payment_data['qr_code_base64'] = transaction_data.get('qr_code_base64')
                        if transaction_data.get('ticket_url'):
                            payment_data['ticket_url'] = transaction_data.get('ticket_url')
            except Exception as e:
                logger.warning(f"Could not fetch MP payment details: {e}")
        
        if payment_data:
            response_data['payment'] = payment_data
        
        return Response(response_data)

    def _notify_checkout_created(self, checkout, cart):
        """Notify automation system about checkout"""
        try:
            from apps.automation.services import AutomationService
            
            # This triggers the automation for cart_created event
            logger.info(f"Checkout created: {checkout.id} for phone {checkout.customer_phone}")
        except Exception as e:
            logger.warning(f"Could not notify checkout: {e}")


class WebhookViewSet(viewsets.GenericViewSet):
    """
    Webhook endpoints for external services.
    
    mercado_pago: POST /api/v1/ecommerce/webhooks/mercado_pago/
    """
    permission_classes = [AllowAny]

    def _get_admin_users(self):
        """Return active superadmin users."""
        return User.objects.filter(is_superuser=True, is_active=True)

    def _notify_admins(self, title: str, message: str, notification_type: str, data: dict, related_type: str, related_id: str):
        """Send notification to all superadmins."""
        service = NotificationService()
        for admin in self._get_admin_users():
            service.create_notification(
                title=title,
                message=message,
                notification_type=notification_type,
                user=admin,
                data=data,
                related_object_type=related_type,
                related_object_id=related_id,
            )

    def _map_mp_payment_method(self, method_id: str) -> str:
        """Map Mercado Pago payment_method_id to Payment method."""
        if not method_id:
            return ''
        method_id = method_id.lower()
        if method_id == 'pix':
            return Payment.PaymentMethod.PIX
        if method_id in ['bolbradesco', 'boleto']:
            return Payment.PaymentMethod.BOLETO
        if method_id in ['visa', 'master', 'mastercard', 'amex', 'elo', 'hipercard']:
            return Payment.PaymentMethod.CREDIT_CARD
        return Payment.PaymentMethod.OTHER

    def _get_or_create_payment(self, checkout: Checkout, result: dict) -> Payment | None:
        """Ensure a Payment record exists for the checkout order."""
        if not checkout.order:
            return None

        payment = Payment.objects.filter(order=checkout.order, is_active=True).order_by('-created_at').first()
        if not payment:
            gateway = PaymentGateway.objects.filter(
                gateway_type=PaymentGateway.GatewayType.MERCADOPAGO,
                is_enabled=True,
                is_active=True
            ).first()
            payment_service = PaymentService()
            payment = payment_service.create_payment(
                order_id=str(checkout.order.id),
                amount=float(checkout.total_amount),
                gateway_id=str(gateway.id) if gateway else None,
                payment_method=self._map_mp_payment_method(result.get('payment_method', '')),
                payer_email=checkout.customer_email,
                payer_name=checkout.customer_name,
                metadata={
                    'source': 'ecommerce',
                    'checkout_id': str(checkout.id),
                    'session_token': checkout.session_token,
                },
            )

        updates = {}
        payment_method = self._map_mp_payment_method(result.get('payment_method', ''))
        if payment_method and not payment.payment_method:
            updates['payment_method'] = payment_method
        if checkout.payment_link and not payment.payment_url:
            updates['payment_url'] = checkout.payment_link
        if result.get('payment_id') and payment.external_id != str(result.get('payment_id')):
            updates['external_id'] = str(result.get('payment_id'))

        if updates:
            for key, value in updates.items():
                setattr(payment, key, value)
            payment.save(update_fields=list(updates.keys()))

        return payment

    @action(detail=False, methods=['post'], url_path='mercado_pago')
    def mercado_pago(self, request):
        """Handle Mercado Pago webhook notifications"""
        logger.info(f"Received MP webhook: {request.data}")
        
        mp_service = MercadoPagoService()
        
        # Verify webhook signature
        x_signature = request.headers.get('x-signature', '')
        x_request_id = request.headers.get('x-request-id', '')
        data_id = str(request.data.get('data', {}).get('id', ''))
        
        if not mp_service.verify_webhook_signature(x_signature, x_request_id, data_id):
            logger.warning(f"Invalid webhook signature for request_id: {x_request_id}")
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        result = mp_service.process_webhook(request.data)
        
        if result.get('success') and result.get('external_reference'):
            # Find checkout by external reference (session_token)
            try:
                checkout = Checkout.objects.get(
                    session_token=result['external_reference']
                )
                
                payment_status = result.get('status')
                if payment_status == 'approved':
                    checkout.payment_status = 'completed'
                    checkout.mercado_pago_payment_id = result.get('payment_id')
                    checkout.mark_completed()
                    self._sync_payment_status(checkout, result)
                    self._notify_payment_confirmed(checkout)
                    
                elif payment_status in ['pending', 'in_process']:
                    checkout.payment_status = 'processing'
                    checkout.save()
                    self._sync_payment_status(checkout, result)
                    
                elif payment_status in ['rejected', 'cancelled']:
                    checkout.payment_status = 'failed'
                    checkout.save()
                    self._sync_payment_status(checkout, result)
                    self._notify_payment_failed(checkout)
                    
            except Checkout.DoesNotExist:
                logger.warning(f"Checkout not found for ref: {result.get('external_reference')}")
        
        return Response({'status': 'ok'})

    def _sync_payment_status(self, checkout: Checkout, result: dict):
        """Sync payment status with payments app."""
        payment = self._get_or_create_payment(checkout, result)
        if not payment:
            return

        payment_status = result.get('status')
        payment_service = PaymentService()

        if payment_status == 'approved':
            payment_service.confirm_payment(
                str(payment.id),
                external_id=str(result.get('payment_id', '')),
                gateway_response=result
            )
        elif payment_status in ['rejected', 'cancelled']:
            payment_service.fail_payment(
                str(payment.id),
                error_code=str(result.get('status_detail', 'failed')),
                error_message='Payment failed',
                gateway_response=result
            )
        elif payment_status in ['pending', 'in_process']:
            if payment.status == Payment.PaymentStatus.PENDING:
                payment.status = Payment.PaymentStatus.PROCESSING
                payment.save(update_fields=['status'])

    def _notify_payment_confirmed(self, checkout):
        """Notify admins about payment confirmation."""
        try:
            if checkout.order:
                self._notify_admins(
                    title='Pagamento confirmado',
                    message=f"Pedido #{checkout.order.order_number} pago com sucesso.",
                    notification_type='payment',
                    data={
                        'order_id': str(checkout.order.id),
                        'order_number': checkout.order.order_number,
                        'checkout_id': str(checkout.id),
                        'amount': float(checkout.total_amount),
                    },
                    related_type='payment',
                    related_id=str(checkout.order.id),
                )
        except Exception as e:
            logger.warning(f"Could not notify payment: {e}")

    def _notify_payment_failed(self, checkout):
        """Notify admins about payment failure."""
        try:
            if checkout.order:
                self._notify_admins(
                    title='Pagamento falhou',
                    message=f"Pedido #{checkout.order.order_number} com pagamento falhado.",
                    notification_type='payment',
                    data={
                        'order_id': str(checkout.order.id),
                        'order_number': checkout.order.order_number,
                        'checkout_id': str(checkout.id),
                        'amount': float(checkout.total_amount),
                    },
                    related_type='payment',
                    related_id=str(checkout.order.id),
                )
        except Exception as e:
            logger.warning(f"Could not notify payment failure: {e}")


class OrdersHistoryView(APIView):
    """
    Orders history API for authenticated users.
    
    GET /api/v1/ecommerce/orders/history/
    Returns user's order history based on completed checkouts.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user's order history from completed checkouts."""
        user = request.user
        
        # Get all checkouts for this user
        checkouts = Checkout.objects.filter(
            user=user
        ).order_by('-created_at')
        
        # Calculate statistics
        completed_checkouts = checkouts.filter(payment_status='completed')
        total_orders = completed_checkouts.count()
        total_spent = completed_checkouts.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        # Build recent orders list
        recent_orders = []
        for checkout in checkouts[:20]:  # Last 20 orders
            # Get items from cart if available
            items = []
            if checkout.cart:
                for cart_item in checkout.cart.items.select_related('product').all():
                    items.append({
                        'id': str(cart_item.id),
                        'product_name': cart_item.product.name,
                        'quantity': cart_item.quantity,
                        'price': float(cart_item.product.price),
                        'subtotal': float(cart_item.get_subtotal()),
                    })
            
            # Map payment_status to order status
            status_map = {
                'pending': 'Pendente',
                'processing': 'Processando',
                'completed': 'Concluído',
                'failed': 'Falhou',
                'cancelled': 'Cancelado',
                'refunded': 'Reembolsado',
            }
            
            recent_orders.append({
                'id': str(checkout.id),
                'order_number': checkout.session_token[:8].upper(),
                'status': status_map.get(checkout.payment_status, checkout.payment_status),
                'total_amount': float(checkout.total_amount),
                'items': items,
                'created_at': checkout.created_at.isoformat(),
                'completed_at': checkout.completed_at.isoformat() if checkout.completed_at else None,
                'shipping_address': checkout.shipping_address,
                'shipping_city': checkout.shipping_city,
                'shipping_state': checkout.shipping_state,
            })
        
        return Response({
            'statistics': {
                'total_orders': total_orders,
                'total_spent': float(total_spent),
            },
            'recent_orders': recent_orders,
        })


class WishlistViewSet(viewsets.GenericViewSet):
    """
    Wishlist/Favorites API.
    
    list: GET /api/v1/ecommerce/wishlist/
    add: POST /api/v1/ecommerce/wishlist/add/
    remove: POST /api/v1/ecommerce/wishlist/remove/
    toggle: POST /api/v1/ecommerce/wishlist/toggle/
    """
    serializer_class = WishlistSerializer
    permission_classes = [IsAuthenticated]

    def get_wishlist(self, request):
        """Get or create wishlist for current user"""
        wishlist, created = Wishlist.objects.get_or_create(user=request.user)
        return wishlist

    def list(self, request):
        """Get current user's wishlist"""
        wishlist = self.get_wishlist(request)
        serializer = WishlistSerializer(wishlist, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add(self, request):
        """Add product to wishlist"""
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        product = get_object_or_404(Product, id=product_id, is_active=True)
        wishlist = self.get_wishlist(request)
        wishlist.products.add(product)
        
        return Response({
            'message': 'Product added to wishlist',
            'product_id': str(product.id),
            'wishlist_count': wishlist.products.count()
        })

    @action(detail=False, methods=['post'])
    def remove(self, request):
        """Remove product from wishlist"""
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        product = get_object_or_404(Product, id=product_id)
        wishlist = self.get_wishlist(request)
        wishlist.products.remove(product)
        
        return Response({
            'message': 'Product removed from wishlist',
            'product_id': str(product.id),
            'wishlist_count': wishlist.products.count()
        })

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        """Toggle product in wishlist"""
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        product = get_object_or_404(Product, id=product_id, is_active=True)
        wishlist = self.get_wishlist(request)
        
        if product in wishlist.products.all():
            wishlist.products.remove(product)
            added = False
        else:
            wishlist.products.add(product)
            added = True
        
        return Response({
            'added': added,
            'product_id': str(product.id),
            'wishlist_count': wishlist.products.count()
        })


class CouponViewSet(viewsets.GenericViewSet):
    """
    Coupon/Promo code API.
    
    validate: POST /api/v1/ecommerce/coupons/validate/
    """
    serializer_class = CouponSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def validate(self, request):
        """Validate a coupon code and calculate discount"""
        serializer = ValidateCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        code = serializer.validated_data['code'].upper().strip()
        total = serializer.validated_data['total']
        
        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return Response({
                'valid': False,
                'error': 'Cupom não encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not coupon.is_valid():
            return Response({
                'valid': False,
                'error': 'Cupom expirado ou inválido'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if total < coupon.min_purchase:
            return Response({
                'valid': False,
                'error': f'Compra mínima de R$ {coupon.min_purchase:.2f} para usar este cupom'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        discount = coupon.calculate_discount(total)
        
        return Response({
            'valid': True,
            'code': coupon.code,
            'description': coupon.description,
            'discount_type': coupon.discount_type,
            'discount_value': float(coupon.discount_value),
            'discount_amount': float(discount),
            'final_total': float(total - discount)
        })


class DeliveryViewSet(viewsets.GenericViewSet):
    """
    Delivery fee calculator API.
    
    calculate: POST /api/v1/ecommerce/delivery/calculate/
    zones: GET /api/v1/ecommerce/delivery/zones/
    """
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def calculate(self, request):
        """Calculate delivery fee for a zip code"""
        serializer = DeliveryFeeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        zip_code = serializer.validated_data['zip_code']

        distance_enabled = DeliveryZone.objects.filter(is_active=True).exclude(
            min_km__isnull=True,
            max_km__isnull=True
        ).exists()
        if distance_enabled:
            distance_service = DeliveryDistanceService()
            distance_result = distance_service.calculate_delivery(zip_code)
            if distance_result.get('available'):
                return Response({
                    'available': True,
                    'fee': float(distance_result['fee']),
                    'estimated_days': distance_result['estimated_days'],
                    'zone_name': distance_result['zone_name'],
                    'distance_km': float(distance_result['distance_km']),
                    'duration_min': distance_result.get('duration_min'),
                    'rate_per_km': float(distance_result['rate_per_km']),
                    'min_fee': float(distance_result['min_fee']) if distance_result.get('min_fee') else None,
                })

        result = DeliveryZone.get_fee_for_zip(zip_code)
        if result:
            return Response({
                'available': True,
                'fee': float(result['fee']),
                'estimated_days': result['estimated_days'],
                'zone_name': result['zone_name']
            })

        default_fee = getattr(settings, 'DEFAULT_DELIVERY_FEE', 15.00)
        return Response({
            'available': True,
            'fee': float(default_fee),
            'estimated_days': 3,
            'zone_name': 'Padrão'
        })

    @action(detail=False, methods=['get'])
    def zones(self, request):
        """List all delivery zones"""
        zones = DeliveryZone.objects.filter(is_active=True)
        serializer = DeliveryZoneSerializer(zones, many=True)
        return Response(serializer.data)


class CouponAdminViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for Coupons.
    
    GET    /api/v1/ecommerce/admin/coupons/
    POST   /api/v1/ecommerce/admin/coupons/
    GET    /api/v1/ecommerce/admin/coupons/{id}/
    PATCH  /api/v1/ecommerce/admin/coupons/{id}/
    DELETE /api/v1/ecommerce/admin/coupons/{id}/
    """
    queryset = Coupon.objects.all().order_by('-created_at')
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'discount_type']
    search_fields = ['code', 'description']
    ordering_fields = ['created_at', 'valid_from', 'valid_until', 'used_count']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by validity
        valid_only = self.request.query_params.get('valid_only')
        if valid_only == 'true':
            from django.utils import timezone
            now = timezone.now()
            queryset = queryset.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now
            )
        return queryset
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle coupon active status."""
        coupon = self.get_object()
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'id': str(coupon.id),
            'is_active': coupon.is_active
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get coupon usage statistics."""
        from django.db.models import Sum, Count
        from django.utils import timezone
        
        now = timezone.now()
        total = Coupon.objects.count()
        active = Coupon.objects.filter(
            is_active=True,
            valid_from__lte=now,
            valid_until__gte=now
        ).count()
        total_uses = Coupon.objects.aggregate(total=Sum('used_count'))['total'] or 0
        
        return Response({
            'total_coupons': total,
            'active_coupons': active,
            'total_uses': total_uses
        })


class DeliveryZoneAdminViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for Delivery Zones.
    
    GET    /api/v1/ecommerce/admin/delivery-zones/
    POST   /api/v1/ecommerce/admin/delivery-zones/
    GET    /api/v1/ecommerce/admin/delivery-zones/{id}/
    PATCH  /api/v1/ecommerce/admin/delivery-zones/{id}/
    DELETE /api/v1/ecommerce/admin/delivery-zones/{id}/
    """
    queryset = DeliveryZone.objects.all().order_by('min_km', 'zip_code_start')
    serializer_class = DeliveryZoneSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'zip_code_start', 'zip_code_end']
    ordering_fields = ['name', 'delivery_fee', 'min_km', 'max_km']
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle zone active status."""
        zone = self.get_object()
        zone.is_active = not zone.is_active
        zone.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'id': str(zone.id),
            'is_active': zone.is_active
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get delivery zone statistics."""
        from django.db.models import Avg, Min, Max
        
        total = DeliveryZone.objects.count()
        active = DeliveryZone.objects.filter(is_active=True).count()
        fee_stats = DeliveryZone.objects.filter(is_active=True).aggregate(
            avg_fee=Avg('delivery_fee'),
            min_fee=Min('delivery_fee'),
            max_fee=Max('delivery_fee'),
            avg_days=Avg('estimated_days'),
        )
        
        return Response({
            'total_zones': total,
            'active_zones': active,
            'avg_fee': float(fee_stats['avg_fee'] or 0),
            'min_fee': float(fee_stats['min_fee'] or 0),
            'max_fee': float(fee_stats['max_fee'] or 0),
            'avg_days': float(fee_stats['avg_days'] or 0)
        })


class StoreLocationAdminViewSet(viewsets.ViewSet):
    """Admin config for store location used in delivery distance calculations."""
    permission_classes = [IsAuthenticated]

    def list(self, request):
        location = StoreLocation.objects.filter(is_active=True).order_by('-updated_at').first()
        if not location:
            return Response({})
        return Response(StoreLocationSerializer(location).data)

    def create(self, request):
        serializer = StoreLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        zip_code = serializer.validated_data['zip_code']
        distance_service = DeliveryDistanceService()
        geo = distance_service.get_zip_location(zip_code)
        if not geo:
            return Response({'error': 'CEP inválido ou não encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

        location = StoreLocation.objects.filter(is_active=True).order_by('-updated_at').first()
        if not location:
            location = StoreLocation()

        location.name = serializer.validated_data.get('name', location.name or '')
        location.zip_code = distance_service.normalize_zip(zip_code)
        location.address = serializer.validated_data.get('address') or geo.address
        location.city = serializer.validated_data.get('city') or geo.city
        location.state = serializer.validated_data.get('state') or geo.state
        location.latitude = geo.latitude
        location.longitude = geo.longitude
        location.is_active = True
        location.save()

        StoreLocation.objects.filter(is_active=True).exclude(id=location.id).update(is_active=False)

        return Response(StoreLocationSerializer(location).data, status=status.HTTP_201_CREATED)
