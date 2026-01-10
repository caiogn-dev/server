"""
E-commerce API views - compatible with Pastita frontend.
"""
import logging
import uuid
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from ..models import Product, Cart, CartItem, Checkout
from .serializers import (
    ProductSerializer,
    CartSerializer,
    CartItemSerializer,
    AddToCartSerializer,
    UpdateCartItemSerializer,
    RemoveFromCartSerializer,
    CheckoutSerializer,
    CreateCheckoutSerializer,
)
from ..services import MercadoPagoService

logger = logging.getLogger(__name__)


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

    @action(detail=False, methods=['post'])
    def create_checkout(self, request):
        """Create checkout from cart and generate Mercado Pago preference"""
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
            )
            
            # Update cart with phone number for automation
            cart.phone_number = data['customer_phone']
            cart.save(update_fields=['phone_number'])
            
            # Create Mercado Pago preference
            mp_service = MercadoPagoService()
            if mp_service.is_configured():
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
                    external_reference=session_token,
                )
                
                if result.get('success'):
                    checkout.mercado_pago_preference_id = result.get('preference_id')
                    checkout.payment_link = result.get('init_point')
                    checkout.save(update_fields=[
                        'mercado_pago_preference_id', 'payment_link'
                    ])
                else:
                    logger.error(f"Failed to create MP preference: {result}")
            
            # Notify automation system
            self._notify_checkout_created(checkout, cart)
        
        return Response(CheckoutSerializer(checkout).data, status=status.HTTP_201_CREATED)

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

    @action(detail=False, methods=['post'], url_path='mercado_pago')
    def mercado_pago(self, request):
        """Handle Mercado Pago webhook notifications"""
        logger.info(f"Received MP webhook: {request.data}")
        
        mp_service = MercadoPagoService()
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
                    
                    # Notify automation system
                    self._notify_payment_confirmed(checkout)
                    
                elif payment_status in ['pending', 'in_process']:
                    checkout.payment_status = 'processing'
                    checkout.save()
                    
                elif payment_status in ['rejected', 'cancelled']:
                    checkout.payment_status = 'failed'
                    checkout.save()
                    
                    # Notify automation system
                    self._notify_payment_failed(checkout)
                    
            except Checkout.DoesNotExist:
                logger.warning(f"Checkout not found for ref: {result.get('external_reference')}")
        
        return Response({'status': 'ok'})

    def _notify_payment_confirmed(self, checkout):
        """Notify automation about payment confirmation"""
        try:
            from apps.automation.services import AutomationService
            from apps.automation.models import CompanyProfile, CustomerSession
            
            # Find or create customer session
            phone = checkout.customer_phone
            if phone:
                logger.info(f"Payment confirmed for {phone}, triggering automation")
                # The automation service will handle sending the WhatsApp message
        except Exception as e:
            logger.warning(f"Could not notify payment: {e}")

    def _notify_payment_failed(self, checkout):
        """Notify automation about payment failure"""
        try:
            logger.info(f"Payment failed for {checkout.customer_phone}")
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
