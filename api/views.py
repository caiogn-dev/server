from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authtoken.models import Token
import uuid
import logging
import re

from .models import (
    Product, Cart, CartItem, Order, OrderItem,
    Checkout, PaymentNotification
)
from .serializers import (
    UserSerializer, ProductSerializer, CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, CheckoutSerializer
)
from .mercado_pago import MercadoPagoService

User = get_user_model()
logger = logging.getLogger(__name__)


# CSRF Token endpoint for SPA
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@ensure_csrf_cookie
def get_csrf_token(request):
    """
    Get CSRF token for the frontend.
    This endpoint sets the CSRF cookie and returns the token.
    """
    csrf_token = get_token(request)
    return Response({
        'csrfToken': csrf_token,
        'detail': 'CSRF cookie set'
    })


def validate_cpf(cpf: str) -> bool:
    """Validate Brazilian CPF number."""
    cpf = re.sub(r'[^0-9]', '', cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False
    # First digit validation
    sum_val = sum(int(cpf[i]) * (10 - i) for i in range(9))
    first_digit = (sum_val * 10 % 11) % 10
    if first_digit != int(cpf[9]):
        return False
    # Second digit validation
    sum_val = sum(int(cpf[i]) * (11 - i) for i in range(10))
    second_digit = (sum_val * 10 % 11) % 10
    return second_digit == int(cpf[10])


def validate_phone(phone: str) -> bool:
    """Validate Brazilian phone number (10-11 digits)."""
    phone = re.sub(r'[^0-9]', '', phone)
    return len(phone) >= 10 and len(phone) <= 11


def validate_cep(cep: str) -> bool:
    """Validate Brazilian CEP (8 digits)."""
    cep = re.sub(r'[^0-9]', '', cep)
    return len(cep) == 8


def generate_order_number() -> str:
    """Generate unique order number with date prefix."""
    date_prefix = timezone.now().strftime('%Y%m%d')
    unique_suffix = uuid.uuid4().hex[:8].upper()
    return f"ORD-{date_prefix}-{unique_suffix}"


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for User model with full CRUD and authentication."""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'register']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return User.objects.filter(id=self.request.user.id)
        return User.objects.none()

    @action(detail=False, methods=['get', 'put', 'patch'])
    def profile(self, request):
        """Get or update current user's profile."""
        user = request.user
        if request.method in ['PUT', 'PATCH']:
            partial = request.method == 'PATCH'
            serializer = self.get_serializer(user, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            logger.info(f"User {user.id} updated profile")
            return Response(serializer.data)
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        """Register a new user and return auth token."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        logger.info(f"New user registered: {user.username}")
        return Response({
            'user': serializer.data,
            'token': token.key
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def logout(self, request):
        """Logout user by deleting their auth token."""
        try:
            request.user.auth_token.delete()
            logger.info(f"User {request.user.id} logged out")
            return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Logout error for user {request.user.id}: {str(e)}")
            return Response({'error': 'Logout failed'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change user's password."""
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not old_password or not new_password:
            return Response(
                {'error': 'Both old_password and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not user.check_password(old_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(new_password) < 8:
            return Response(
                {'error': 'New password must be at least 8 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.set_password(new_password)
        user.save()
        logger.info(f"User {user.id} changed password")
        return Response({'message': 'Password changed successfully'})


class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet for Product model with search, filtering, and pagination."""
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'search', 'categories', 'featured']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
    
    def get_queryset(self):
        """Filter products with optional query parameters."""
        queryset = Product.objects.filter(is_active=True)
        
        # Price range filtering
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        # In stock filtering
        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() == 'true':
            queryset = queryset.filter(stock_quantity__gt=0)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search products by name, description, or SKU."""
        query = request.query_params.get('q', '').strip()
        category = request.query_params.get('category', '').strip()
        
        products = self.get_queryset()
        
        if query:
            from django.db.models import Q
            products = products.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(sku__icontains=query)
            )
        
        if category:
            products = products.filter(category__iexact=category)
        
        # Apply ordering
        ordering = request.query_params.get('ordering', '-created_at')
        if ordering in ['price', '-price', 'name', '-name', 'created_at', '-created_at']:
            products = products.order_by(ordering)
        
        serializer = self.get_serializer(products, many=True)
        return Response({
            'count': products.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all unique product categories with counts."""
        from django.db.models import Count
        categories = (
            self.get_queryset()
            .values('category')
            .annotate(count=Count('id'))
            .order_by('category')
        )
        return Response({
            'categories': [
                {'name': cat['category'], 'count': cat['count']}
                for cat in categories if cat['category']
            ]
        })

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured/popular products (top 6 by stock)."""
        products = self.get_queryset().filter(stock_quantity__gt=0).order_by('-stock_quantity')[:6]
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def check_stock(self, request, pk=None):
        """Check if product is in stock with requested quantity."""
        product = self.get_object()
        quantity = int(request.query_params.get('quantity', 1))
        return Response({
            'product_id': str(product.id),
            'requested_quantity': quantity,
            'available_quantity': product.stock_quantity,
            'in_stock': product.stock_quantity >= quantity
        })


class CartViewSet(viewsets.ViewSet):
    """ViewSet for shopping cart operations with stock validation."""
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, user):
        """Get or create cart for user."""
        cart, created = Cart.objects.get_or_create(user=user)
        if created:
            logger.info(f"Created new cart for user {user.id}")
        return cart

    def list(self, request):
        """Get current user's cart with all items."""
        cart = self.get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart with stock validation."""
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        
        # Validate quantity
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid quantity format'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if quantity <= 0:
            return Response(
                {'error': 'Quantity must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get product
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check existing cart item
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product,
            defaults={'quantity': 0}
        )
        
        new_quantity = cart_item.quantity + quantity
        
        # Validate stock
        if new_quantity > product.stock_quantity:
            return Response({
                'error': 'Insufficient stock',
                'available': product.stock_quantity,
                'requested': new_quantity,
                'current_in_cart': cart_item.quantity
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cart_item.quantity = new_quantity
        cart_item.save()
        
        logger.info(f"User {request.user.id} added {quantity}x {product.name} to cart")
        
        return Response({
            'message': 'Item added to cart',
            'item': CartItemSerializer(cart_item).data,
            'cart_total': float(cart.get_total()),
            'cart_count': cart.get_item_count()
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        """Remove item from cart."""
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        
        if not product_id:
            return Response(
                {'error': 'product_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        deleted_count, _ = CartItem.objects.filter(cart=cart, product_id=product_id).delete()
        
        if deleted_count == 0:
            return Response(
                {'error': 'Item not found in cart'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        logger.info(f"User {request.user.id} removed product {product_id} from cart")
        
        return Response({
            'message': 'Item removed from cart',
            'cart_total': float(cart.get_total()),
            'cart_count': cart.get_item_count()
        })

    @action(detail=False, methods=['post'])
    def update_item(self, request):
        """Update item quantity in cart with stock validation."""
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity')
        
        if not product_id:
            return Response(
                {'error': 'product_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid quantity format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If quantity is 0 or less, remove the item
        if quantity <= 0:
            CartItem.objects.filter(cart=cart, product_id=product_id).delete()
            return Response({
                'message': 'Item removed from cart',
                'cart_total': float(cart.get_total()),
                'cart_count': cart.get_item_count()
            })

        try:
            cart_item = CartItem.objects.select_related('product').get(
                cart=cart, product_id=product_id
            )
        except CartItem.DoesNotExist:
            return Response(
                {'error': 'Item not found in cart'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate stock
        if quantity > cart_item.product.stock_quantity:
            return Response({
                'error': 'Insufficient stock',
                'available': cart_item.product.stock_quantity,
                'requested': quantity
            }, status=status.HTTP_400_BAD_REQUEST)
        
        cart_item.quantity = quantity
        cart_item.save()
        
        return Response({
            'message': 'Cart updated',
            'item': CartItemSerializer(cart_item).data,
            'cart_total': float(cart.get_total()),
            'cart_count': cart.get_item_count()
        })

    @action(detail=False, methods=['post'])
    def clear(self, request):
        """Clear all items from cart."""
        cart = self.get_cart(request.user)
        count = cart.items.count()
        cart.items.all().delete()
        logger.info(f"User {request.user.id} cleared cart ({count} items)")
        return Response({
            'message': 'Cart cleared',
            'items_removed': count
        })

    @action(detail=False, methods=['get'])
    def validate(self, request):
        """Validate cart items against current stock and prices."""
        cart = self.get_cart(request.user)
        items = cart.items.select_related('product').all()
        
        issues = []
        valid_items = []
        
        for item in items:
            product = item.product
            item_issues = []
            
            if not product.is_active:
                item_issues.append('Product is no longer available')
            
            if item.quantity > product.stock_quantity:
                item_issues.append(f'Only {product.stock_quantity} available (you have {item.quantity})')
            
            if item_issues:
                issues.append({
                    'product_id': str(product.id),
                    'product_name': product.name,
                    'issues': item_issues
                })
            else:
                valid_items.append({
                    'product_id': str(product.id),
                    'product_name': product.name,
                    'quantity': item.quantity,
                    'price': float(product.price)
                })
        
        return Response({
            'valid': len(issues) == 0,
            'valid_items': valid_items,
            'issues': issues,
            'cart_total': float(cart.get_total()),
            'cart_count': cart.get_item_count()
        })


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for order management with full history and details."""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get orders for current user only."""
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        """Get all items for a specific order."""
        order = self.get_object()
        serializer = OrderItemSerializer(order.items.all(), many=True)
        return Response({
            'order_id': str(order.id),
            'order_number': order.order_number,
            'items': serializer.data,
            'total': float(order.total_amount)
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order if it's still pending."""
        order = self.get_object()
        
        if order.status not in ['pending']:
            return Response(
                {'error': f'Cannot cancel order with status: {order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = 'cancelled'
        order.save()
        
        # Restore stock
        for item in order.items.all():
            item.product.stock_quantity += item.quantity
            item.product.save()
        
        logger.info(f"Order {order.order_number} cancelled by user {request.user.id}")
        
        return Response({
            'message': 'Order cancelled successfully',
            'order_number': order.order_number,
            'status': order.status
        })

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get order history with summary statistics."""
        orders = self.get_queryset()
        
        from django.db.models import Sum, Count
        stats = orders.aggregate(
            total_orders=Count('id'),
            total_spent=Sum('total_amount')
        )
        
        serializer = self.get_serializer(orders[:20], many=True)
        
        return Response({
            'statistics': {
                'total_orders': stats['total_orders'] or 0,
                'total_spent': float(stats['total_spent'] or 0)
            },
            'recent_orders': serializer.data
        })


class CheckoutViewSet(viewsets.ViewSet):
    """
    Complete checkout process with:
    1. Cart validation and stock verification
    2. Order creation with all required fields
    3. Mercado Pago payment preference generation
    4. Checkout record creation for tracking
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def create_checkout(self, request):
        """Create order and payment preference from cart."""
        user = request.user
        buyer_data = request.data.get('buyer', {})
        
        # Extract and validate buyer information
        buyer_name = buyer_data.get('name', '').strip()
        buyer_email = buyer_data.get('email', user.email or '').strip()
        buyer_cpf = buyer_data.get('cpf', '').strip()
        buyer_phone = buyer_data.get('phone', user.phone or '').strip()
        buyer_address = buyer_data.get('address', user.address or '').strip()
        buyer_city = buyer_data.get('city', user.city or '').strip()
        buyer_state = buyer_data.get('state', user.state or '').strip()
        buyer_zip_code = buyer_data.get('zip_code', user.zip_code or '').strip()
        
        # Validate required fields
        errors = {}
        if not buyer_name:
            errors['name'] = 'Nome é obrigatório'
        if not buyer_email:
            errors['email'] = 'E-mail é obrigatório'
        elif not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', buyer_email):
            errors['email'] = 'E-mail inválido'
        if not buyer_phone:
            errors['phone'] = 'Telefone é obrigatório'
        elif not validate_phone(buyer_phone):
            errors['phone'] = 'Telefone inválido (10-11 dígitos)'
        if not buyer_address:
            errors['address'] = 'Endereço é obrigatório'
        if not buyer_city:
            errors['city'] = 'Cidade é obrigatória'
        if not buyer_state:
            errors['state'] = 'Estado é obrigatório'
        if not buyer_zip_code:
            errors['zip_code'] = 'CEP é obrigatório'
        elif not validate_cep(buyer_zip_code):
            errors['zip_code'] = 'CEP inválido (8 dígitos)'
        
        # Validate CPF if provided
        if buyer_cpf and not validate_cpf(buyer_cpf):
            errors['cpf'] = 'CPF inválido'
        
        if errors:
            return Response(
                {'error': 'Validation failed', 'details': errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get cart
        try:
            cart = Cart.objects.get(user=user)
        except Cart.DoesNotExist:
            return Response(
                {'error': 'Cart not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_items = cart.items.select_related('product').all()
        
        if not cart_items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate stock for all items
        stock_errors = []
        for item in cart_items:
            if not item.product.is_active:
                stock_errors.append(f'{item.product.name} is no longer available')
            elif item.quantity > item.product.stock_quantity:
                stock_errors.append(
                    f'{item.product.name}: only {item.product.stock_quantity} available, '
                    f'you requested {item.quantity}'
                )
        
        if stock_errors:
            return Response(
                {'error': 'Stock validation failed', 'details': stock_errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate total from backend (never trust frontend prices)
        total_amount = sum(item.product.price * item.quantity for item in cart_items)
        
        # Generate unique order number
        order_number = generate_order_number()
        
        # Create Order with all required fields
        order = Order.objects.create(
            user=user,
            order_number=order_number,
            total_amount=total_amount,
            status='pending',
            shipping_address=buyer_address,
            shipping_city=buyer_city,
            shipping_state=buyer_state,
            shipping_zip_code=buyer_zip_code,
            shipping_country='Brazil',
            notes=f"Customer: {buyer_name}, Email: {buyer_email}, Phone: {buyer_phone}"
        )

        # Create OrderItems and update stock
        order_items = []
        for item in cart_items:
            order_items.append(OrderItem(
                order=order,
                product=item.product,
                price=item.product.price,
                quantity=item.quantity
            ))
            # Decrease stock
            item.product.stock_quantity -= item.quantity
            item.product.save()
        
        OrderItem.objects.bulk_create(order_items)

        # Create Checkout record for tracking
        session_token = uuid.uuid4().hex
        checkout = Checkout.objects.create(
            order=order,
            user=user,
            total_amount=total_amount,
            payment_status='pending',
            session_token=session_token,
            customer_name=buyer_name,
            customer_email=buyer_email,
            customer_phone=buyer_phone,
            billing_address=buyer_address,
            billing_city=buyer_city,
            billing_state=buyer_state,
            billing_zip_code=buyer_zip_code,
            billing_country='Brazil',
            expires_at=timezone.now() + timezone.timedelta(hours=24)
        )

        # Clear cart
        cart.items.all().delete()

        # Create Mercado Pago preference
        try:
            mp_service = MercadoPagoService()
            preference = mp_service.create_preference_from_order(order, {
                'name': buyer_name,
                'email': buyer_email,
                'cpf': buyer_cpf,
                'phone': buyer_phone
            })
            
            # Update checkout with MP preference ID
            checkout.mercado_pago_preference_id = preference.get('id')
            checkout.payment_link = preference.get('init_point')
            checkout.save()

            logger.info(
                f"Checkout created: Order {order_number}, "
                f"User {user.id}, Total R${total_amount}"
            )

            return Response({
                'success': True,
                'order_id': str(order.id),
                'order_number': order_number,
                'checkout_id': str(checkout.id),
                'session_token': session_token,
                'total_amount': float(total_amount),
                'init_point': preference.get('init_point'),
                'sandbox_init_point': preference.get('sandbox_init_point'),
                'preference_id': preference.get('id')
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Mercado Pago error for order {order_number}: {str(e)}")
            # Rollback will happen due to transaction.atomic
            return Response(
                {'error': 'Payment service error', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def status(self, request):
        """Check checkout status by session token or order ID."""
        session_token = request.query_params.get('token')
        order_id = request.query_params.get('order_id')
        
        if not session_token and not order_id:
            return Response(
                {'error': 'Either token or order_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if session_token:
                checkout = Checkout.objects.select_related('order').get(
                    session_token=session_token,
                    user=request.user
                )
            else:
                checkout = Checkout.objects.select_related('order').get(
                    order_id=order_id,
                    user=request.user
                )
        except Checkout.DoesNotExist:
            return Response(
                {'error': 'Checkout not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'checkout_id': str(checkout.id),
            'order_id': str(checkout.order.id),
            'order_number': checkout.order.order_number,
            'payment_status': checkout.payment_status,
            'order_status': checkout.order.status,
            'total_amount': float(checkout.total_amount),
            'payment_link': checkout.payment_link,
            'created_at': checkout.created_at.isoformat(),
            'expires_at': checkout.expires_at.isoformat() if checkout.expires_at else None
        })

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get checkout history for current user."""
        checkouts = Checkout.objects.filter(user=request.user).select_related('order').order_by('-created_at')[:20]
        
        return Response({
            'checkouts': [
                {
                    'checkout_id': str(c.id),
                    'order_number': c.order.order_number,
                    'total_amount': float(c.total_amount),
                    'payment_status': c.payment_status,
                    'order_status': c.order.status,
                    'created_at': c.created_at.isoformat()
                }
                for c in checkouts
            ]
        })


class WebhookViewSet(viewsets.ViewSet):
    """
    Webhook handlers for external payment notifications.
    All webhooks are public but should be verified.
    """
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'], url_path='mercado_pago')
    def mercado_pago(self, request):
        """
        Handle Mercado Pago payment notifications.
        
        MP sends notifications in two formats:
        1. IPN (Instant Payment Notification): topic + id
        2. Webhooks: type + data.id
        """
        try:
            payload = request.data
            
            # Log incoming webhook for debugging
            logger.info(f"MP Webhook received: {payload}")
            
            # Handle empty payload gracefully
            if not payload:
                logger.warning("Empty webhook payload received")
                return Response({'message': 'Empty payload'}, status=status.HTTP_200_OK)

            # Extract topic and resource ID from either format
            topic = payload.get('topic') or payload.get('type')
            resource_id = payload.get('id') or payload.get('data', {}).get('id')
            action = payload.get('action', '')
            
            if not topic or not resource_id:
                logger.warning(f"Invalid webhook format: topic={topic}, id={resource_id}")
                return Response({'message': 'Invalid format'}, status=status.HTTP_200_OK)

            logger.info(f"Processing MP webhook: topic={topic}, id={resource_id}, action={action}")

            mp_service = MercadoPagoService()
            
            if topic == 'payment':
                success = mp_service.process_payment_notification(resource_id, payload)
                if success:
                    logger.info(f"Payment {resource_id} processed successfully")
                else:
                    logger.warning(f"Payment {resource_id} processing returned False")
                    
            elif topic == 'merchant_order':
                mp_service.process_merchant_order(resource_id, payload)
                
            elif topic == 'chargebacks':
                logger.warning(f"Chargeback notification received: {resource_id}")
                # Handle chargebacks - mark order as disputed
                
            else:
                logger.info(f"Unhandled webhook topic: {topic}")

            # Always return 200 to acknowledge receipt
            return Response({'message': 'Received', 'topic': topic}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
            # Still return 200 to prevent MP from retrying indefinitely
            return Response({'message': 'Error logged'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='mercado_pago')
    def mercado_pago_verify(self, request):
        """
        Handle MP webhook verification (GET request).
        MP may send GET to verify endpoint is active.
        """
        return Response({'status': 'active', 'service': 'mercado_pago'})


class HealthCheckView(APIView):
    """Health check endpoint for monitoring."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        from django.db import connection
        
        health = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'services': {}
        }
        
        # Check database
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            health['services']['database'] = 'ok'
        except Exception as e:
            health['services']['database'] = f'error: {str(e)}'
            health['status'] = 'degraded'
        
        # Check Mercado Pago configuration
        if settings.MERCADO_PAGO_ACCESS_TOKEN:
            health['services']['mercado_pago'] = 'configured'
        else:
            health['services']['mercado_pago'] = 'not configured'
            health['status'] = 'degraded'
        
        # Check AWS S3 configuration
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            health['services']['aws_s3'] = 'configured'
        else:
            health['services']['aws_s3'] = 'not configured'
        
        status_code = status.HTTP_200_OK if health['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(health, status=status_code)