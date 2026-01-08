from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Count, F, Sum, Q
from django.conf import settings
from django.utils import timezone
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from decimal import Decimal
from datetime import timedelta
import uuid
import logging
import re

from .models import Product, Cart, CartItem, Order, OrderItem, Checkout, PaymentNotification
from .serializers import (
    UserSerializer, ProductSerializer, CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, CheckoutSerializer, AdminUserSerializer
)
from .panel_webhook import send_panel_webhook
from .mercado_pago import MercadoPagoService

User = get_user_model()
logger = logging.getLogger(__name__)

SHIPPING_FLAT_FEE = Decimal('15.00')
PICKUP_ADDRESS = "Q. 112 Sul Rua SR 1, conj. 06 lote 04 - Plano Diretor Sul"
PICKUP_CITY = "Palmas"
PICKUP_STATE = "TO"
PICKUP_ZIP = "77020-170"


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@ensure_csrf_cookie
def get_csrf_token(request):
    csrf_token = get_token(request)
    return Response({'csrfToken': csrf_token, 'detail': 'CSRF cookie set'})


def validate_cpf(cpf: str) -> bool:
    cpf = re.sub(r'[^0-9]', '', cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False
    sum_val = sum(int(cpf[i]) * (10 - i) for i in range(9))
    first_digit = (sum_val * 10 % 11) % 10
    if first_digit != int(cpf[9]):
        return False
    sum_val = sum(int(cpf[i]) * (11 - i) for i in range(10))
    second_digit = (sum_val * 10 % 11) % 10
    return second_digit == int(cpf[10])


def validate_phone(phone: str) -> bool:
    phone = re.sub(r'[^0-9]', '', phone)
    return 10 <= len(phone) <= 11


def normalize_phone(phone: str) -> str:
    if not phone:
        return ''
    return re.sub(r'[^0-9]', '', phone)


def validate_cep(cep: str) -> bool:
    cep = re.sub(r'[^0-9]', '', cep)
    return len(cep) == 8


def generate_order_number() -> str:
    date_prefix = timezone.now().strftime('%Y%m%d')
    unique_suffix = uuid.uuid4().hex[:8].upper()
    return f"ORD-{date_prefix}-{unique_suffix}"


@method_decorator(csrf_exempt, name='dispatch')
class EmailOrPhoneAuthToken(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        login_value = request.data.get('login') or request.data.get('email') or request.data.get('phone')
        password = request.data.get('password')

        if not login_value or not password:
            return Response({'error': 'Informe email ou celular e senha.'}, status=status.HTTP_400_BAD_REQUEST)

        login_value = str(login_value).strip()
        user = None

        if '@' in login_value:
            user = User.objects.filter(email__iexact=login_value).first()
        else:
            phone = normalize_phone(login_value)
            if phone:
                matches = User.objects.filter(phone=phone)
                if matches.count() > 1:
                    return Response({'error': 'Celular duplicado. Entre em contato com o suporte.'}, status=status.HTTP_400_BAD_REQUEST)
                user = matches.first()

        if not user or not user.check_password(password):
            return Response({'error': 'Credenciais invalidas.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({'error': 'Usuario inativo.'}, status=status.HTTP_403_FORBIDDEN)

        token, _ = Token.objects.get_or_create(user=user)
        response = Response({
            'token': token.key,
            'user': {
                'id': str(user.id),
                'email': user.email,
                'phone': user.phone,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
        })
        cookie_kwargs = {
            'httponly': True,
            'secure': settings.AUTH_COOKIE_SECURE,
            'samesite': settings.AUTH_COOKIE_SAMESITE,
            'path': '/',
        }
        if settings.AUTH_COOKIE_DOMAIN:
            cookie_kwargs['domain'] = settings.AUTH_COOKIE_DOMAIN
        response.set_cookie(settings.AUTH_COOKIE_NAME, token.key, **cookie_kwargs)
        return response


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ['create', 'register']:
            return [permissions.AllowAny()]
        if self.action in ['profile', 'logout', 'change_password']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        user = request.user
        if request.method.lower() == 'get':
            return Response(UserSerializer(user).data)
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def logout(self, request):
        try:
            Token.objects.filter(user=request.user).delete()
        except Exception:
            pass
        response = Response({'detail': 'Logged out'})
        response.delete_cookie(settings.AUTH_COOKIE_NAME, path='/')
        return response

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        if not current_password or not new_password:
            return Response({'error': 'Informe a senha atual e a nova senha.'}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(current_password):
            return Response({'error': 'Senha atual incorreta.'}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_password)
        request.user.save()
        return Response({'detail': 'Senha atualizada com sucesso.'})


class ProductViewSet(viewsets.ModelViewSet):
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
        queryset = Product.objects.filter(is_active=True)
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() == 'true':
            queryset = queryset.filter(stock_quantity__gt=0)
        return queryset

    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '').strip()
        category = request.query_params.get('category', '').strip()
        products = self.get_queryset()
        if query:
            from django.db.models import Q
            products = products.filter(
                Q(name__icontains=query) | Q(description__icontains=query) | Q(sku__icontains=query)
            )
        if category:
            products = products.filter(category__iexact=category)
        ordering = request.query_params.get('ordering', '-created_at')
        if ordering in ['price', '-price', 'name', '-name', 'created_at', '-created_at']:
            products = products.order_by(ordering)
        serializer = self.get_serializer(products, many=True)
        return Response({'count': products.count(), 'results': serializer.data})

    @action(detail=False, methods=['get'])
    def categories(self, request):
        categories = (
            self.get_queryset().values('category').annotate(count=Count('id')).order_by('category')
        )
        return Response({'categories': [{'name': cat['category'], 'count': cat['count']} for cat in categories if cat['category']]})

    @action(detail=False, methods=['get'])
    def featured(self, request):
        products = self.get_queryset().filter(stock_quantity__gt=0).order_by('-stock_quantity')[:6]
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def check_stock(self, request, pk=None):
        product = self.get_object()
        quantity = int(request.query_params.get('quantity', 1))
        return Response({'product_id': str(product.id), 'requested_quantity': quantity, 'available_quantity': product.stock_quantity, 'in_stock': product.stock_quantity >= quantity})


class CartViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    def list(self, request):
        cart = self._get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1) or 1)
        if quantity < 1:
            quantity = 1
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({'error': 'Produto nao encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        if product.stock_quantity < quantity:
            return Response({'error': 'Quantidade indisponivel em estoque.'}, status=status.HTTP_400_BAD_REQUEST)
        cart = self._get_cart(request.user)
        item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={'quantity': quantity})
        if not created:
            item.quantity = item.quantity + quantity
            item.save(update_fields=['quantity', 'updated_at'])
        serializer = CartItemSerializer(item)
        return Response({'item': serializer.data, 'cart': CartSerializer(cart).data})

    @action(detail=False, methods=['post'])
    def update_item(self, request):
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1) or 1)
        if quantity < 1:
            quantity = 1
        cart = self._get_cart(request.user)
        try:
            item = CartItem.objects.get(cart=cart, product_id=product_id)
        except CartItem.DoesNotExist:
            return Response({'error': 'Item nao encontrado no carrinho.'}, status=status.HTTP_404_NOT_FOUND)
        if item.product.stock_quantity < quantity:
            return Response({'error': 'Quantidade indisponivel em estoque.'}, status=status.HTTP_400_BAD_REQUEST)
        item.quantity = quantity
        item.save(update_fields=['quantity', 'updated_at'])
        serializer = CartItemSerializer(item)
        return Response({'item': serializer.data, 'cart': CartSerializer(cart).data})

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        product_id = request.data.get('product_id')
        cart = self._get_cart(request.user)
        CartItem.objects.filter(cart=cart, product_id=product_id).delete()
        return Response({'cart': CartSerializer(cart).data})

    @action(detail=False, methods=['post'])
    def clear(self, request):
        cart = self._get_cart(request.user)
        cart.items.all().delete()
        return Response({'cart': CartSerializer(cart).data})


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def history(self, request):
        orders = self.get_queryset()[:10]
        serializer = self.get_serializer(orders, many=True)
        return Response({'recent_orders': serializer.data})


class CheckoutViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    def _validate_shipping(self, shipping_method: str, buyer: dict):
        shipping_method = (shipping_method or 'delivery').lower()
        if shipping_method not in ['delivery', 'pickup']:
            shipping_method = 'delivery'
        if shipping_method == 'pickup':
            return shipping_method, PICKUP_ADDRESS, PICKUP_CITY, PICKUP_STATE, PICKUP_ZIP, Decimal('0.00'), {}

        address = (buyer.get('address') or '').strip()
        city = (buyer.get('city') or '').strip()
        state = (buyer.get('state') or '').strip()
        zip_code = re.sub(r'[^0-9]', '', str(buyer.get('zip_code') or ''))
        errors = {}
        if not address:
            errors['address'] = 'Endereco obrigatorio para entrega.'
        if not city:
            errors['city'] = 'Cidade obrigatoria para entrega.'
        if not state:
            errors['state'] = 'Estado obrigatorio para entrega.'
        if not validate_cep(zip_code):
            errors['zip_code'] = 'CEP invalido.'
        if errors:
            return shipping_method, None, None, None, None, SHIPPING_FLAT_FEE, errors
        return shipping_method, address, city, state, zip_code, SHIPPING_FLAT_FEE, {}

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def create_checkout(self, request):
        user = request.user
        cart = self._get_cart(user)
        cart_items = list(cart.items.select_related('product'))
        if not cart_items:
            return Response({'error': 'Carrinho vazio.'}, status=status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        buyer = payload.get('buyer') or {}
        payment_data = payload.get('payment') or {}
        shipping_method = payload.get('shipping_method') or buyer.get('shipping_method') or 'delivery'

        shipping_method, ship_addr, ship_city, ship_state, ship_zip, shipping_fee, shipping_errors = self._validate_shipping(shipping_method, buyer)
        if shipping_errors:
            return Response({'details': shipping_errors}, status=status.HTTP_400_BAD_REQUEST)

        cart_total = Decimal('0.00')
        for item in cart_items:
            if item.product.stock_quantity < item.quantity:
                return Response({'error': f"Estoque insuficiente para {item.product.name}"}, status=status.HTTP_400_BAD_REQUEST)
            cart_total += Decimal(item.product.price) * item.quantity

        total_amount = cart_total + shipping_fee

        order = Order.objects.create(
            user=user,
            order_number=generate_order_number(),
            total_amount=total_amount,
            status='pending',
            shipping_address=ship_addr,
            shipping_city=ship_city,
            shipping_state=ship_state,
            shipping_zip_code=ship_zip,
            shipping_country='Brazil',
            notes=f"shipping_method={shipping_method}; shipping_fee={shipping_fee}"
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                quantity=item.quantity,
                price=item.product.price
            )
            item.product.stock_quantity = F('stock_quantity') - item.quantity
            item.product.save(update_fields=['stock_quantity'])

        cart.items.all().delete()

        checkout = Checkout.objects.create(
            order=order,
            user=user,
            total_amount=total_amount,
            payment_status='pending',
            payment_method=None,
            session_token=uuid.uuid4().hex,
            payment_link=None,
            customer_name=buyer.get('name') or user.get_full_name() or 'Cliente',
            customer_email=buyer.get('email') or user.email,
            customer_phone=normalize_phone(buyer.get('phone') or user.phone or ''),
            billing_address=ship_addr,
            billing_city=ship_city,
            billing_state=ship_state,
            billing_zip_code=ship_zip,
            billing_country='Brazil'
        )

        customer_name = buyer.get('name') or user.get_full_name() or user.email

        send_panel_webhook(
            "order_created",
            {
                "order_number": order.order_number,
                "status": order.status,
                "total_amount": float(order.total_amount),
                "created_at": order.created_at.isoformat(),
                "customer_name": customer_name,
            },
        )

        mp_service = MercadoPagoService()
        response_payload = {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'payment_status': checkout.payment_status,
            'shipping_method': shipping_method,
            'shipping_fee': float(shipping_fee),
            'total_amount': float(total_amount)
        }

        try:
            if payment_data:
                payment = mp_service.create_payment_from_order(order, {
                    'name': buyer.get('name'),
                    'email': buyer.get('email'),
                    'phone': buyer.get('phone'),
                    'cpf': buyer.get('cpf'),
                }, payment_data)
                checkout.payment_method = payment_data.get('method') or payment_data.get('payment_method')
                checkout.mercado_pago_payment_id = str(payment.get('id')) if payment else None
                checkout.payment_status = payment.get('status') if payment else checkout.payment_status
                checkout.save()
                response_payload['payment'] = payment
            else:
                pref = mp_service.create_preference_from_order(order, {
                    'name': buyer.get('name'),
                    'email': buyer.get('email'),
                    'phone': buyer.get('phone'),
                    'cpf': buyer.get('cpf'),
                })
                checkout.mercado_pago_preference_id = pref.get('id') if pref else None
                checkout.payment_link = pref.get('init_point') if pref else None
                checkout.save()
                response_payload.update(pref or {})
        except Exception as exc:
            logger.error('Erro ao criar pagamento: %s', exc, exc_info=True)
            response_payload['payment_error'] = str(exc)

        return Response(response_payload, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def status(self, request):
        order_number = request.query_params.get('order_number')
        if not order_number:
            return Response({'error': 'order_number obrigatorio'}, status=status.HTTP_400_BAD_REQUEST)
        order = None
        if request.user and request.user.is_authenticated:
            order = Order.objects.filter(order_number=order_number, user=request.user).first()
        if not order:
            order = Order.objects.filter(order_number=order_number).first()
        if not order:
            return Response({'error': 'Pedido nao encontrado'}, status=status.HTTP_404_NOT_FOUND)
        checkout = Checkout.objects.filter(order=order).first()
        data = {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'order_status': order.status,
            'payment_status': checkout.payment_status if checkout else order.status,
            'total_amount': float(order.total_amount),
            'shipping_address': order.shipping_address,
            'shipping_city': order.shipping_city,
            'shipping_state': order.shipping_state,
            'shipping_zip_code': order.shipping_zip_code,
        }
        if checkout:
            data['checkout'] = CheckoutSerializer(checkout).data
            if checkout.mercado_pago_payment_id:
                try:
                    mp_service = MercadoPagoService()
                    payment = mp_service.get_payment_info(checkout.mercado_pago_payment_id)
                    data['payment'] = payment
                except Exception:
                    pass
        return Response(data)


class WebhookViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'], url_path='mercado_pago')
    def mercado_pago(self, request):
        payload = request.data or {}
        notification_id = payload.get('data', {}).get('id') or payload.get('id')
        topic = payload.get('type') or payload.get('topic')
        logger.info('Webhook recebido: topic=%s id=%s', topic, notification_id)

        if topic == 'payment' and notification_id:
            mp_service = MercadoPagoService()
            ok = mp_service.process_payment_notification(notification_id, payload)
            if ok:
                return Response({'detail': 'processed'})
        return Response({'detail': 'received'})


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'status': 'ok'})


class AdminViewSet(viewsets.ViewSet):
    """
    Endpoints administrativos para o painel.
    Protegido por permissão de admin.
    """
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        now = timezone.now()
        today_orders_qs = Order.objects.filter(created_at__date=now.date())

        today_revenue = today_orders_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        today_orders = today_orders_qs.count()
        pending_orders = Order.objects.filter(status='pending').count()
        active_users_24h = (
            Order.objects.filter(created_at__gte=now - timedelta(hours=24))
            .values('user')
            .distinct()
            .count()
        )

        return Response({
            'today_revenue': float(today_revenue),
            'today_orders': today_orders,
            'pending_orders': pending_orders,
            'active_users': active_users_24h,
        })

    @action(detail=False, methods=['get'])
    def orders(self, request):
        qs = Order.objects.all().select_related('user').order_by('-created_at')

        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        total = qs.count()
        qs = qs[offset:offset + limit]

        results = []
        for order in qs:
            results.append({
                'order_number': order.order_number,
                'customer_name': order.user.get_full_name() or order.user.email,
                'status': order.status,
                'total_amount': float(order.total_amount),
                'shipping_method': 'pickup' if 'pickup' in (order.notes or '') else 'delivery',
                'created_at': order.created_at,
            })

        return Response({
            'count': total,
            'results': results,
        })


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminUserSerializer
    queryset = User.objects.all().order_by('-date_joined')

    def list(self, request):
        qs = self.get_queryset()
        query = (request.query_params.get('q') or '').strip()
        if query:
            qs = qs.filter(
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(phone__icontains=query)
            )

        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        total = qs.count()
        qs = qs[offset:offset + limit]
        serializer = self.get_serializer(qs, many=True)
        return Response({'count': total, 'results': serializer.data})


class AdminProductViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductSerializer
    queryset = Product.objects.all().order_by('-created_at')

    def list(self, request):
        qs = self.get_queryset()
        query = (request.query_params.get('q') or '').strip()
        if query:
            qs = qs.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(sku__icontains=query)
            )
        is_active = request.query_params.get('is_active')
        if is_active in ['true', 'false']:
            qs = qs.filter(is_active=is_active == 'true')

        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        total = qs.count()
        qs = qs[offset:offset + limit]
        serializer = self.get_serializer(qs, many=True)
        return Response({'count': total, 'results': serializer.data})

