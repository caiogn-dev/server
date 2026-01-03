from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
import uuid

from .models import (
    Product, Cart, CartItem, Order, OrderItem,
    Checkout, PaymentNotification
)
from .serializers import (
    UserSerializer, ProductSerializer, CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, CheckoutSerializer,
    CheckoutCreateSerializer, PaymentNotificationSerializer, WebhookPayloadSerializer
)
from .mercado_pago import MercadoPagoService
from .permissions import IsOwnerOrReadOnly, IsOwner

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for User model"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return User.objects.filter(id=self.request.user.id)
        return User.objects.none()

    @action(detail=False, methods=['get', 'put'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        """Get or update current user profile"""
        user = request.user
        if request.method == 'PUT':
            serializer = self.get_serializer(user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Product model"""
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['price', 'created_at', 'name']

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search products by name or category"""
        query = request.query_params.get('q', '')
        category = request.query_params.get('category', '')

        products = self.queryset
        if query:
            products = products.filter(name__icontains=query) | \
                       products.filter(description__icontains=query)
        if category:
            products = products.filter(category=category)

        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all available categories"""
        categories = self.queryset.values_list('category', flat=True).distinct()
        return Response({'categories': list(categories)})


class CartViewSet(viewsets.ViewSet):
    """ViewSet for Cart operations"""
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, user):
        """Get or create cart for user"""
        cart, created = Cart.objects.get_or_create(user=user)
        return cart

    def list(self, request):
        """Get user's cart"""
        cart = self.get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart"""
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if quantity <= 0:
            return Response(
                {'error': 'Quantity must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if quantity > product.stock_quantity:
            return Response(
                {'error': f'Only {product.stock_quantity} items available'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )

        if not created:
            cart_item.quantity += quantity
            if cart_item.quantity > product.stock_quantity:
                return Response(
                    {'error': f'Only {product.stock_quantity} items available'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cart_item.save()

        serializer = CartItemSerializer(cart_item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        """Remove item from cart"""
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')

        try:
            cart_item = CartItem.objects.get(cart=cart, product_id=product_id)
            cart_item.delete()
            return Response({'message': 'Item removed from cart'})
        except CartItem.DoesNotExist:
            return Response(
                {'error': 'Item not found in cart'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'])
    def update_item(self, request):
        """Update item quantity in cart"""
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)

        try:
            cart_item = CartItem.objects.get(cart=cart, product_id=product_id)
            product = cart_item.product

            if quantity <= 0:
                cart_item.delete()
                return Response({'message': 'Item removed from cart'})

            if quantity > product.stock_quantity:
                return Response(
                    {'error': f'Only {product.stock_quantity} items available'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cart_item.quantity = quantity
            cart_item.save()

            serializer = CartItemSerializer(cart_item)
            return Response(serializer.data)
        except CartItem.DoesNotExist:
            return Response(
                {'error': 'Item not found in cart'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'])
    def clear(self, request):
        """Clear the cart"""
        cart = self.get_cart(request.user)
        cart.items.all().delete()
        return Response({'message': 'Cart cleared'})


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for Order model"""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return orders for current user"""
        return Order.objects.filter(user=self.request.user)

    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        """Get items in an order"""
        order = self.get_object()
        items = order.items.all()
        serializer = OrderItemSerializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update order status (admin only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        order = self.get_object()
        status_choice = request.data.get('status')

        valid_choices = [choice[0] for choice in Order.ORDER_STATUS_CHOICES]
        if status_choice not in valid_choices:
            return Response(
                {'error': f'Invalid status. Must be one of {valid_choices}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = status_choice
        order.save()
        serializer = self.get_serializer(order)
        return Response(serializer.data)


class CheckoutViewSet(viewsets.ViewSet):
    """ViewSet for Checkout operations"""
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    def create_checkout(self, request):
        """Create a checkout session from cart"""
        user = request.user
        cart = get_object_or_404(Cart, user=user)

        if not cart.items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CheckoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                # Create order
                order = Order.objects.create(
                    user=user,
                    order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
                    total_amount=cart.get_total(),
                    status='pending',
                    shipping_address=serializer.validated_data['billing_address'],
                    shipping_city=serializer.validated_data['billing_city'],
                    shipping_state=serializer.validated_data['billing_state'],
                    shipping_zip_code=serializer.validated_data['billing_zip_code'],
                    shipping_country=serializer.validated_data.get('billing_country', 'Brazil')
                )

                # Create order items from cart
                for cart_item in cart.items.all():
                    OrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price=cart_item.product.price
                    )

                # Create checkout
                checkout = Checkout.objects.create(
                    order=order,
                    user=user,
                    total_amount=order.total_amount,
                    payment_status='pending',
                    payment_method=serializer.validated_data['payment_method'],
                    session_token=str(uuid.uuid4()),
                    customer_name=serializer.validated_data['customer_name'],
                    customer_email=serializer.validated_data['customer_email'],
                    customer_phone=serializer.validated_data['customer_phone'],
                    billing_address=serializer.validated_data['billing_address'],
                    billing_city=serializer.validated_data['billing_city'],
                    billing_state=serializer.validated_data['billing_state'],
                    billing_zip_code=serializer.validated_data['billing_zip_code'],
                    billing_country=serializer.validated_data.get('billing_country', 'Brazil')
                )

                # Generate Mercado Pago preference
                mp_service = MercadoPagoService()
                preference_id = mp_service.create_preference(checkout)

                if preference_id:
                    checkout.mercado_pago_preference_id = preference_id
                    checkout.payment_link = mp_service.get_payment_link(preference_id)
                    checkout.save()

                # Clear cart
                cart.items.all().delete()

                response_serializer = CheckoutSerializer(checkout)
                return Response(
                    response_serializer.data,
                    status=status.HTTP_201_CREATED
                )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def list(self, request):
        """Get user's checkouts"""
        checkouts = Checkout.objects.filter(user=request.user)
        serializer = CheckoutSerializer(checkouts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def details(self, request):
        """Get checkout details by session token"""
        token = request.query_params.get('token')
        if not token:
            return Response(
                {'error': 'Token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        checkout = get_object_or_404(Checkout, session_token=token)
        serializer = CheckoutSerializer(checkout)
        return Response(serializer.data)


class WebhookViewSet(viewsets.ViewSet):
    """ViewSet for handling Mercado Pago webhooks"""
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'])
    def mercado_pago(self, request):
        """Handle Mercado Pago payment notifications"""
        serializer = WebhookPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payload = request.data
            mp_service = MercadoPagoService()
            
            # Process webhook based on type
            if payload.get('topic') == 'payment':
                payment_id = payload.get('id')
                processed = mp_service.process_payment_notification(
                    payment_id, payload
                )
                if processed:
                    return Response(
                        {'message': 'Webhook processed successfully'},
                        status=status.HTTP_200_OK
                    )

            elif payload.get('topic') == 'merchant_order':
                merchant_order_id = payload.get('id')
                processed = mp_service.process_merchant_order(
                    merchant_order_id, payload
                )
                if processed:
                    return Response(
                        {'message': 'Webhook processed successfully'},
                        status=status.HTTP_200_OK
                    )

            return Response(
                {'message': 'Webhook received'},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
