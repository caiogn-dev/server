from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings

from .models import (
    Product, Cart, CartItem, Order, OrderItem,
    Checkout
)
from .serializers import (
    UserSerializer, ProductSerializer, CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, CheckoutSerializer
)
from .mercado_pago import MercadoPagoService

User = get_user_model()

# --- VIEWSETS ---

class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for User model"""
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

    @action(detail=False, methods=['get', 'put'])
    def profile(self, request):
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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet for Product model"""
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['price', 'created_at', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'search', 'categories']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
    
    @action(detail=False, methods=['get'])
    def search(self, request):
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
        categories = self.queryset.values_list('category', flat=True).distinct()
        return Response({'categories': list(categories)})


class CartViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    def list(self, request):
        cart = self.get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        product = get_object_or_404(Product, id=product_id)

        if quantity <= 0:
            return Response({'error': 'Quantity must be > 0'}, status=status.HTTP_400_BAD_REQUEST)

        cart_item, _ = CartItem.objects.get_or_create(
            cart=cart, product=product,
            defaults={'quantity': 0}
        )
        
        cart_item.quantity += quantity
        cart_item.save()

        return Response(CartItemSerializer(cart_item).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        CartItem.objects.filter(cart=cart, product_id=product_id).delete()
        return Response({'message': 'Item removed'})

    @action(detail=False, methods=['post'])
    def update_item(self, request):
        cart = self.get_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        
        if quantity <= 0:
            CartItem.objects.filter(cart=cart, product_id=product_id).delete()
            return Response({'message': 'Item removed'})

        cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
        cart_item.quantity = quantity
        cart_item.save()
        return Response(CartItemSerializer(cart_item).data)

    @action(detail=False, methods=['post'])
    def clear(self, request):
        cart = self.get_cart(request.user)
        cart.items.all().delete()
        return Response({'message': 'Cart cleared'})


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        order = self.get_object()
        serializer = OrderItemSerializer(order.items.all(), many=True)
        return Response(serializer.data)


class CheckoutViewSet(viewsets.ViewSet):
    """
    Gerencia o processo de Checkout:
    1. Valida Carrinho
    2. Cria Order
    3. Gera Preferência no Mercado Pago
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    @transaction.atomic # Se der erro, desfaz a criação da Order
    def create_checkout(self, request):
        user = request.user
        
        # 1. Busca o carrinho atual do banco (NUNCA CONFIE NO FRONTEND PARA ITENS/PREÇOS)
        try:
            cart = Cart.objects.get(user=user)
        except Cart.DoesNotExist:
             return Response({'error': 'Cart is empty'}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = cart.items.all().select_related('product')
        
        if not cart_items.exists():
            return Response({'error': 'Cart is empty'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Cria o Pedido (Order)
        # Calcula total aqui no backend
        total_amount = sum(item.product.price * item.quantity for item in cart_items)
        
        order = Order.objects.create(
            user=user,
            total_amount=total_amount,
            status='pending' # Status inicial
        )

        # 3. Move itens do Cart para OrderItem
        order_items = []
        for item in cart_items:
            order_items.append(OrderItem(
                order=order,
                product=item.product,
                price=item.product.price, # Preço congelado no momento da compra
                quantity=item.quantity
            ))
        
        OrderItem.objects.bulk_create(order_items)

        # 4. Limpa o carrinho
        cart.items.all().delete()

        # 5. Chama o Service do Mercado Pago
        try:
            mp_service = MercadoPagoService()
            # Passamos o objeto Order, o service deve extrair os dados de lá de forma segura
            preference = mp_service.create_preference_from_order(order, request.data.get('buyer', {}))
            
            # (Opcional) Salvar ID da preferência no Checkout ou Order se tiver campo pra isso
            # Checkout.objects.create(order=order, external_id=preference['id']...)

            return Response({
                "order_id": order.id,
                "init_point": preference['init_point'], 
                "sandbox_init_point": preference.get('sandbox_init_point')
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # O transaction.atomic vai dar rollback na Order se cair aqui
            raise ValidationError(f"Error creating payment preference: {str(e)}")


class WebhookViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'])
    def mercado_pago(self, request):
        try:
            payload = request.data
            # Validação básica pra não quebrar se vier vazio
            if not payload:
                return Response({'message': 'Empty payload'}, status=status.HTTP_200_OK)

            mp_service = MercadoPagoService()
            
            topic = payload.get('topic') or payload.get('type')
            resource_id = payload.get('id') or payload.get('data', {}).get('id')

            if topic == 'payment':
                mp_service.process_payment_notification(resource_id, payload)
            elif topic == 'merchant_order':
                mp_service.process_merchant_order(resource_id, payload)

            return Response({'message': 'Received'}, status=status.HTTP_200_OK)
        except Exception as e:
            # Logar o erro aqui seria bom
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)