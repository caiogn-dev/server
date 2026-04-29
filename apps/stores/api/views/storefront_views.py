"""
Storefront API views for public store access.

These views handle cart, checkout, catalog, and wishlist functionality
for the public-facing storefront.
"""
import logging
from decimal import Decimal
from urllib.parse import urlparse
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView


class PublicReadThrottle(AnonRateThrottle):
    """300/min for read-only public catalog — storefront browsing is high-frequency."""
    scope = 'public_read'

class PublicWriteThrottle(AnonRateThrottle):
    """60/min for cart mutations — protects against cart-spam, allows normal use."""
    scope = 'public_write'

class CheckoutThrottle(AnonRateThrottle):
    """20/min per IP — protects against bot ordering while allowing legitimate retries."""
    scope = 'checkout'
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

from apps.core.models import UserProfile
from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import (
    Store, StoreProduct, StoreCategory, StoreCart, StoreCartItem,
    StoreCombo, StoreProductType, StoreCoupon, StoreDeliveryZone,
    StoreCustomer, StorePaymentGateway,
    StoreWishlist
)
from apps.stores.services import cart_service, checkout_service
from apps.stores.services.geo import geo_service
from apps.stores.services.realtime_service import broadcast_order_event
from ..serializers import (
    StoreSerializer, StoreCategorySerializer, StoreProductSerializer,
    StoreCartSerializer, StoreCartItemSerializer, StoreComboSerializer,
    CatalogProductTypeSerializer, StoreWishlistSerializer, WishlistAddRemoveSerializer
)

logger = logging.getLogger(__name__)

_STORE_CACHE_TTL = 60  # seconds — store config changes are rare
_CATALOG_CACHE_TTL = 300  # 5 min — catalog changes are infrequent


def get_active_store(slug: str):
    """
    Return the active Store for *slug*, with a 60-second cache per slug.

    Uses Django's cache framework (Redis in production, LocMem in dev).
    Cache is invalidated automatically by TTL; explicit invalidation happens
    in store save signals if implemented.
    """
    from django.core.cache import cache
    from django.http import Http404

    cache_key = f'store:slug:{slug}'
    store = cache.get(cache_key)
    if store is None:
        store = Store.objects.filter(slug=slug, status='active').select_related('owner').first()
        if store is None:
            raise Http404(f"Store '{slug}' not found or not active")
        cache.set(cache_key, store, _STORE_CACHE_TTL)
    return store


def get_request_cart_key(request):
    """Resolve a stable cart key for anonymous storefront requests."""
    header_cart_key = (
        request.headers.get('X-Cart-Key')
        or request.META.get('HTTP_X_CART_KEY')
        or ''
    ).strip()
    if header_cart_key:
        return header_cart_key[:255]

    query_cart_key = (request.query_params.get('cart_key') or '').strip()
    if query_cart_key:
        return query_cart_key[:255]

    try:
        payload_cart_key = (request.data.get('cart_key') or '').strip()
    except Exception:
        payload_cart_key = ''

    if payload_cart_key:
        return payload_cart_key[:255]

    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key

    return session_id


def get_request_origin_base(request):
    """Resolve the originating storefront base URL from request headers."""
    for header_name in ('Origin', 'Referer'):
        raw_value = (request.headers.get(header_name) or '').strip()
        if not raw_value:
            continue

        parsed = urlparse(raw_value)
        if parsed.scheme and parsed.netloc:
            return f'{parsed.scheme}://{parsed.netloc}'

    return ''


def build_store_payment_config(store):
    """Return the safe public payment configuration for the mobile storefront."""
    mercadopago_gateway = (
        StorePaymentGateway.objects.filter(
            store=store,
            gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
            is_enabled=True,
        )
        .order_by('-is_default', 'name')
        .first()
    )
    credentials = checkout_service.get_payment_credentials(store)

    public_key = ''
    if mercadopago_gateway and mercadopago_gateway.public_key:
        public_key = mercadopago_gateway.public_key
    elif isinstance(store.metadata, dict):
        public_key = str(store.metadata.get('mercadopago_public_key') or '').strip()

    if not public_key and getattr(settings, 'MERCADO_PAGO_PUBLIC_KEY', ''):
        public_key = getattr(settings, 'MERCADO_PAGO_PUBLIC_KEY', '')

    enabled_methods = []
    if credentials:
        enabled_methods.append('pix')
    if credentials and public_key:
        enabled_methods.append('credit_card')
    if (store.metadata or {}).get('cash_enabled', True):
        enabled_methods.append('cash')

    return {
        'enabled_methods': enabled_methods,
        'mercado_pago': {
            'public_key': public_key,
            'is_sandbox': bool(
                (mercadopago_gateway.is_sandbox if mercadopago_gateway else False)
                or (credentials or {}).get('sandbox', False)
            ),
            'native_card_supported': bool(public_key),
        },
    }


def build_store_customer_profile(store, user):
    """Build a merged customer profile payload for the storefront app."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    store_customer, _ = StoreCustomer.objects.get_or_create(store=store, user=user)

    addresses = store_customer.addresses if isinstance(store_customer.addresses, list) else []
    default_index = store_customer.default_address_index or 0
    default_address = addresses[default_index] if 0 <= default_index < len(addresses) else None

    def _looks_placeholder(value: str) -> bool:
        value = (value or '').strip().lower()
        return (
            not value
            or value.startswith('cliente_')
            or value == 'desconhecido'
            or value.endswith('@pastita.local')
        )

    full_name = f"{user.first_name} {user.last_name}".strip()
    if _looks_placeholder(full_name):
        from apps.core.services.customer_identity import CustomerIdentityService
        from apps.conversations.models import Conversation
        from apps.users.models import UnifiedUser

        phones = set(CustomerIdentityService.phone_candidates(profile.phone or ''))
        conversation_name = (
            Conversation.objects
            .filter(phone_number__in=phones)
            .exclude(contact_name='')
            .order_by('-last_message_at', '-created_at')
            .values_list('contact_name', flat=True)
            .first()
        )
        unified_name = (
            UnifiedUser.objects
            .filter(phone_number__in=phones)
            .exclude(name__iexact='desconhecido')
            .values_list('name', flat=True)
            .first()
        )
        full_name = next(
            (candidate for candidate in [conversation_name, unified_name, user.username, user.email] if not _looks_placeholder(candidate)),
            ''
        )

    return {
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        },
        'contact': {
            'name': full_name,
            'email': user.email,
            'phone': profile.phone,
            'cpf': profile.cpf,
        },
        'profile': {
            'address': profile.address,
            'city': profile.city,
            'state': profile.state,
            'zip_code': profile.zip_code,
        },
        'addresses': addresses,
        'default_address_index': default_index,
        'default_address': default_address,
        'stats': {
            'total_orders': store_customer.total_orders,
            'total_spent': float(store_customer.total_spent or 0),
            'last_order_at': store_customer.last_order_at.isoformat() if store_customer.last_order_at else None,
        },
        'loyalty': checkout_service.get_loyalty_status(store, user),
        'preferences': {
            'accepts_marketing': store_customer.accepts_marketing,
        },
    }


class StorePublicView(APIView):
    """Public store information endpoint."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicReadThrottle]

    def get(self, request, store_slug):
        """Get public store information."""
        store = get_active_store(store_slug)
        serializer = StoreSerializer(store)
        return Response(serializer.data)


class StoreCatalogView(APIView):
    """Public catalog endpoint for a store."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicReadThrottle]

    def get(self, request, store_slug):
        """Get store catalog with categories, products, and combos."""
        from django.core.cache import cache

        store = get_active_store(store_slug)
        cache_key = f'catalog:{store_slug}'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Single query for all active products — evaluated once, grouped in Python
        all_products = list(
            StoreProduct.objects.filter(store=store, status='active')
            .select_related('category')
            .order_by('sort_order', 'name')
        )

        categories = list(
            StoreCategory.objects.filter(store=store, is_active=True)
            .order_by('sort_order', 'name')
        )

        # Group products by category_id in Python — no extra DB hits per category
        from collections import defaultdict
        products_by_cat_id = defaultdict(list)
        for p in all_products:
            products_by_cat_id[p.category_id].append(p)

        products_by_category = []
        for category in categories:
            cat_products = products_by_cat_id.get(category.id, [])
            if cat_products:
                products_by_category.append({
                    'category': StoreCategorySerializer(category).data,
                    'products': StoreProductSerializer(cat_products, many=True).data,
                })

        featured_products = [p for p in all_products if p.featured]

        combos = list(
            StoreCombo.objects.filter(store=store, is_active=True)
            .prefetch_related('items__product')
            .order_by('sort_order', 'name')
        )
        combos_destaque = [c for c in combos if c.featured]

        product_types = list(
            StoreProductType.objects.filter(store=store, is_active=True)
            .order_by('sort_order', 'name')
        )

        payload = {
            'store': StoreSerializer(store).data,
            'categories': StoreCategorySerializer(categories, many=True).data,
            'products': StoreProductSerializer(all_products, many=True).data,
            'featured_products': StoreProductSerializer(featured_products, many=True).data,
            'combos': StoreComboSerializer(combos, many=True).data,
            'combos_destaque': StoreComboSerializer(combos_destaque, many=True).data,
            'product_types': CatalogProductTypeSerializer(product_types, many=True).data,
            'products_by_category': products_by_category,
        }
        cache.set(cache_key, payload, _CATALOG_CACHE_TTL)
        return Response(payload)


class StoreAppConfigView(APIView):
    """Public bootstrap config for the native storefront app."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicReadThrottle]

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        whatsapp_account = store.get_whatsapp_account()
        payment_config = build_store_payment_config(store)
        metadata = store.metadata or {}

        return Response({
            'auth': {
                'whatsapp_otp_enabled': bool(whatsapp_account),
                'whatsapp_account_id': str(whatsapp_account.id) if whatsapp_account else '',
            },
            'payment': payment_config,
            'delivery': {
                'city': store.city or '',
                'state': store.state or '',
                'delivery_enabled': bool(store.delivery_enabled),
                'pickup_enabled': bool(store.pickup_enabled),
                'store_coords': {
                    'lat': float(store.latitude) if store.latitude is not None else None,
                    'lng': float(store.longitude) if store.longitude is not None else None,
                },
                'default_delivery_fee': float(store.default_delivery_fee or 0),
                'min_order_value': float(store.min_order_value or 0),
                'free_delivery_threshold': float(store.free_delivery_threshold or 0) if store.free_delivery_threshold else None,
                'max_distance_km': float(metadata.get('max_delivery_distance_km', 20)),
                'max_time_minutes': float(metadata.get('max_delivery_time_minutes', 45)),
            },
            'branding': {
                'primary_color': store.primary_color or '',
                'secondary_color': store.secondary_color or '',
                'logo_url': store.get_logo_url(),
                'banner_url': store.get_banner_url(),
            },
        })


class StoreCustomerProfileView(APIView):
    """Customer storefront profile scoped to the selected store."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PublicReadThrottle]

    def get_store(self, store_slug):
        return get_active_store(store_slug)

    def get(self, request, store_slug):
        store = self.get_store(store_slug)
        return Response(build_store_customer_profile(store, request.user))

    def patch(self, request, store_slug):
        store = self.get_store(store_slug)
        data = request.data or {}

        name = str(data.get('customer_name') or data.get('name') or '').strip()
        email = str(data.get('customer_email') or data.get('email') or request.user.email or '').strip()
        phone = str(data.get('customer_phone') or data.get('phone') or '').strip()
        cpf = str(data.get('cpf') or '').strip()

        address = data.get('address')
        addresses = data.get('addresses')
        delivery_address = {}
        if isinstance(address, dict):
            delivery_address = address
        elif isinstance(addresses, list) and addresses:
            first_address = addresses[0]
            if isinstance(first_address, dict):
                delivery_address = first_address

        customer_record = CustomerIdentityService.sync_checkout_customer(
            store=store,
            customer_name=name,
            email=email,
            phone=phone,
            cpf=cpf,
            delivery_method='delivery' if delivery_address else '',
            delivery_address=delivery_address,
            user=request.user,
        )

        store_customer = customer_record.get('store_customer')
        if store_customer:
            if isinstance(addresses, list):
                store_customer.addresses = addresses
            default_index = data.get('default_address_index')
            if default_index is not None:
                try:
                    store_customer.default_address_index = max(0, int(default_index))
                except (TypeError, ValueError):
                    pass
            if 'accepts_marketing' in data:
                store_customer.accepts_marketing = bool(data.get('accepts_marketing'))
            store_customer.save()

        return Response(build_store_customer_profile(store, request.user))


@method_decorator(csrf_exempt, name='dispatch')
class StoreCartViewSet(viewsets.ViewSet):
    """ViewSet for managing shopping carts."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicWriteThrottle]
    
    def get_store(self, store_slug):
        return get_active_store(store_slug)
    
    def get_cart(self, request, store):
        """Get or create cart for session/user."""
        session_id = get_request_cart_key(request)
        user = request.user if request.user.is_authenticated else None
        return cart_service.get_or_create_cart(store, user, session_id)
    
    def get_cart_with_prefetch(self, request, store):
        """Get cart with prefetched related objects to avoid N+1 queries."""
        cart = self.get_cart(request, store)
        # Prefetch related objects to avoid N+1 queries when serializing
        return StoreCart.objects.prefetch_related(
            'items__product',
            'items__variant',
            'combo_items__combo'
        ).get(id=cart.id)
    
    def get_cart_by_store(self, request, store_slug=None):
        """Get cart for a specific store."""
        store = self.get_store(store_slug)
        cart = self.get_cart_with_prefetch(request, store)
        serializer = StoreCartSerializer(cart)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def add_item(self, request, store_slug=None):
        """
        Add item to cart.
        
        Supports both products and combos:
        - For products: send product_id, quantity, variant_id (optional), notes (optional)
        - For combos: send combo_id, quantity, customizations (optional), notes (optional)
        """
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        product_id = request.data.get('product_id')
        combo_id = request.data.get('combo_id')
        quantity = int(request.data.get('quantity', 1))
        notes = request.data.get('notes', '')
        
        combo_name = request.data.get('combo_name', '')
        unit_price = request.data.get('unit_price')
        is_virtual_combo = not combo_id and combo_name

        # Validate: need product_id, combo_id, or virtual combo fields
        if not product_id and not combo_id and not is_virtual_combo:
            return Response(
                {'error': 'product_id, combo_id, or combo_name+unit_price is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if is_virtual_combo:
                # Virtual combo (e.g. salad builder) — no real StoreCombo FK
                if unit_price is None:
                    return Response(
                        {'error': 'unit_price is required for virtual combos'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                customizations = request.data.get('customizations', {})
                if customizations.get('is_salad_builder') or customizations.get('type') == 'custom_salad':
                    customizations = checkout_service.normalize_custom_salad_payload(
                        customizations,
                        combo_name=combo_name,
                        unit_price=unit_price,
                    )
                from decimal import Decimal
                cart_service.add_combo(
                    cart,
                    combo=None,
                    quantity=quantity,
                    customizations=customizations,
                    notes=notes,
                    combo_name=combo_name,
                    unit_price=Decimal(str(unit_price)),
                )
            elif combo_id:
                # Real combo
                customizations = request.data.get('customizations', {})
                combo = StoreCombo.objects.get(id=combo_id, store=store, is_active=True)
                cart_service.add_combo(cart, combo, quantity, customizations, notes)
            else:
                # Product
                variant_id = request.data.get('variant_id')
                cart_service.add_item(cart, product_id, quantity, variant_id, notes)

            return Response(StoreCartSerializer(cart).data)
        except StoreCombo.DoesNotExist:
            return Response(
                {'error': 'Combo not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['patch'], url_path='item/(?P<item_id>[^/.]+)')
    def update_item(self, request, store_slug=None, item_id=None):
        """Update cart item quantity."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        quantity = request.data.get('quantity')
        if quantity is not None:
            quantity = int(quantity)
            if quantity <= 0:
                cart_service.remove_item(cart, item_id)
            else:
                cart_service.update_item_quantity(cart, item_id, quantity)
        
        return Response(StoreCartSerializer(cart).data)
    
    @action(detail=False, methods=['delete'], url_path='item/(?P<item_id>[^/.]+)')
    def remove_item(self, request, store_slug=None, item_id=None):
        """Remove item from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.remove_item(cart, item_id)
        return Response(StoreCartSerializer(cart).data)
    
    @action(detail=False, methods=['delete'])
    def clear_cart(self, request, store_slug=None):
        """Clear all items from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.clear_cart(cart)
        return Response(StoreCartSerializer(cart).data)


@method_decorator(csrf_exempt, name='dispatch')
class StoreCheckoutView(APIView):
    """Checkout endpoint for creating orders."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [CheckoutThrottle]
    
    def post(self, request, store_slug):
        """Process checkout and create order."""
        store = get_active_store(store_slug)
        
        # Get cart
        session_id = get_request_cart_key(request)
        user = request.user if request.user.is_authenticated else None
        cart = cart_service.get_or_create_cart(store, user, session_id)
        
        if not cart.items.exists() and not cart.combo_items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract customer data (checkout_service expects 'name', 'email', 'phone')
        customer_data = {
            'name': request.data.get('customer_name', ''),
            'email': request.data.get('customer_email', ''),
            'phone': request.data.get('customer_phone', ''),
            'cpf': request.data.get('cpf', ''),
        }
        
        # Extract delivery data
        delivery_method = request.data.get('delivery_method') or request.data.get('shipping_method') or 'delivery'
        delivery_data = {
            'method': delivery_method,
            'address': request.data.get('delivery_address', {}),
            'notes': request.data.get('delivery_notes', ''),
            'distance_km': request.data.get('delivery_distance_km'),
            'zip_code': request.data.get('delivery_zip_code'),
        }
        
        coupon_code = request.data.get('coupon_code', '')
        notes = request.data.get('customer_notes') or request.data.get('notes', '')
        payment_method = request.data.get('payment_method', 'pix')
        payment_payload = dict(request.data.get('payment', {}) or {})
        request_origin_base = get_request_origin_base(request)
        if request_origin_base:
            payment_payload['redirect_base_url'] = request_origin_base
        
        try:
            order = checkout_service.create_order(
                cart=cart,
                customer_data=customer_data,
                delivery_data=delivery_data,
                coupon_code=coupon_code,
                notes=notes,
                use_loyalty_reward=bool(
                    request.data.get('use_loyalty_reward')
                    or request.data.get('loyalty_reward')
                ),
            )

            request.session['customer_name'] = order.customer_name or ''
            request.session['customer_email'] = order.customer_email or ''
            request.session['customer_phone'] = order.customer_phone or ''
            request.session.modified = True
            
            # Process payment if method specified
            payment_result = None
            if payment_method:
                payment_result = checkout_service.create_payment(
                    order, payment_method, payment_payload
                )

            payment_failed = bool(payment_result and not payment_result.get('success'))
            if not payment_failed:
                try:
                    from apps.stores.services.meta_pixel_service import send_purchase_event
                    meta_tracking = request.data.get('meta') if isinstance(request.data.get('meta'), dict) else {}
                    send_purchase_event(order, request=request, tracking_data=meta_tracking)
                except Exception as exc:
                    logger.warning("Meta CAPI Purchase failed for %s: %s", order.order_number, exc)

            broadcast_order_event(order, event_type='order.created')
             
            # Clear cart after successful order
            cart_service.clear_cart(cart)
            
            response_data = {
                'order_id': str(order.id),
                'order_number': order.order_number,
                'total': str(order.total),
                'total_amount': float(order.total),
                'payment_status': order.payment_status,
                'access_token': order.access_token,
                'items': [
                    {
                        'id': str(item.id),
                        'product_name': item.product_name,
                        'variant_name': item.variant_name,
                        'quantity': item.quantity,
                        'unit_price': float(item.unit_price),
                        'subtotal': float(item.subtotal),
                        'customizations': item.options,
                        'is_custom_salad': bool(
                            isinstance(item.options, dict)
                            and (
                                item.options.get('is_salad_builder')
                                or item.options.get('type') == 'custom_salad'
                            )
                        ),
                    }
                    for item in order.items.all()
                ],
                'delivery_quote': (order.metadata or {}).get('delivery_quote', {}),
                'loyalty': checkout_service.get_loyalty_status(store, order.customer),
                'loyalty_reward': (order.metadata or {}).get('loyalty_reward', {}),
                'customer': {
                    'user_id': str(order.customer_id) if order.customer_id else '',
                    'name': order.customer_name,
                    'email': order.customer_email,
                    'phone': order.customer_phone,
                },
            }
            
            # Include payment data if available
            if payment_result:
                if payment_result.get('success'):
                    response_data['payment'] = {
                        'status': payment_result.get('status', 'pending'),
                        'payment_id': payment_result.get('payment_id'),
                        'payment_method': payment_result.get('payment_method', payment_method),
                        'status_detail': payment_result.get('status_detail', ''),
                        'requires_redirect': payment_result.get('requires_redirect', False),
                        'init_point': payment_result.get('init_point', ''),
                        'sandbox_init_point': payment_result.get('sandbox_init_point', ''),
                        'checkout_url': payment_result.get('init_point') or payment_result.get('sandbox_init_point') or '',
                    }
                    response_data['pix_code'] = payment_result.get('pix_code', '')
                    response_data['pix_qr_code'] = payment_result.get('pix_qr_code', '')
                    response_data['pix_ticket_url'] = payment_result.get('ticket_url', '')
                    response_data['init_point'] = payment_result.get('init_point', '')
                    response_data['sandbox_init_point'] = payment_result.get('sandbox_init_point', '')
                else:
                    response_data['payment_error'] = payment_result.get('error', 'Erro no pagamento')
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Checkout error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class StoreDeliveryFeeView(APIView):
    """Calculate delivery fee endpoint."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicWriteThrottle]

    def _calculate(self, request, store_slug):
        """Calculate delivery fee from either query params or JSON payload."""
        store = get_active_store(store_slug)

        lat = request.data.get('lat') or request.query_params.get('lat')
        lng = request.data.get('lng') or request.query_params.get('lng')
        address = request.data.get('address') or request.query_params.get('address')
        zip_code = request.data.get('zip_code') or request.query_params.get('zip_code')
        distance_km = request.data.get('distance_km') or request.query_params.get('distance_km')

        if distance_km is not None:
            try:
                delivery_info = checkout_service.calculate_delivery_fee(
                    store,
                    distance_km=Decimal(str(distance_km)),
                    zip_code=zip_code,
                )
                return Response(checkout_service.normalize_delivery_quote(delivery_info))
            except Exception as e:
                logger.error(f"Delivery fee calculation error: {e}")
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if not (lat and lng) and not address and not zip_code:
            return Response(
                {'error': 'Either lat/lng, address, or zip_code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # If only address or zip code provided, geocode it first
            if not (lat and lng):
                geocode_target = address or zip_code
                geocode_result = geo_service.geocode(geocode_target)
                if geocode_result:
                    lat = geocode_result.get('lat')
                    lng = geocode_result.get('lng')
                else:
                    return Response(
                        {'error': 'Could not geocode address'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            delivery_info = geo_service.calculate_delivery_fee(
                store, float(lat), float(lng)
            )
            return Response(checkout_service.normalize_delivery_quote(delivery_info))
        except Exception as e:
            logger.error(f"Delivery fee calculation error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def get(self, request, store_slug):
        """Backward-compatible GET handler used by legacy storefronts."""
        return self._calculate(request, store_slug)

    def post(self, request, store_slug):
        """Calculate delivery fee for an address."""
        return self._calculate(request, store_slug)


class StoreCouponValidateView(APIView):
    """Validate coupon code endpoint."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicWriteThrottle]

    def post(self, request, store_slug):
        """Validate a coupon code."""
        store = get_active_store(store_slug)
        
        code = request.data.get('code')
        subtotal = Decimal(str(request.data.get('subtotal', 0)))
        
        if not code:
            return Response(
                {'error': 'Coupon code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            coupon = StoreCoupon.objects.get(
                store=store,
                code__iexact=code,
                is_active=True
            )
            
            # Check validity (includes min_purchase check)
            valid, error_msg = coupon.is_valid(subtotal=subtotal, user=request.user)
            if not valid:
                return Response({
                    'valid': False,
                    'error': error_msg
                })

            # Calculate discount
            if coupon.discount_type == 'percentage':
                discount = subtotal * (coupon.discount_value / 100)
                if coupon.max_discount:
                    discount = min(discount, coupon.max_discount)
            else:
                discount = coupon.discount_value
            
            return Response({
                'valid': True,
                'coupon': {
                    'code': coupon.code,
                    'discount_type': coupon.discount_type,
                    'discount_value': str(coupon.discount_value),
                    'calculated_discount': str(discount),
                }
            })
        except StoreCoupon.DoesNotExist:
            return Response({
                'valid': False,
                'error': 'Invalid coupon code'
            })


class StoreWishlistViewSet(viewsets.ViewSet):
    """ViewSet for managing user wishlists per store."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicWriteThrottle]

    def get_store(self, store_slug):
        return get_active_store(store_slug)
    
    def _get_customer_id(self, request):
        """Get customer identifier from request."""
        if request.user.is_authenticated:
            return {'customer_email': request.user.email}
        # Try to get from session or request data
        phone = request.data.get('customer_phone') or request.session.get('customer_phone')
        email = request.data.get('customer_email') or request.session.get('customer_email')
        if phone:
            return {'customer_phone': phone}
        if email:
            return {'customer_email': email}
        return None
    
    def list(self, request, store_slug=None):
        """Get user's wishlist for a store."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response({
                'products': [],
                'count': 0
            })
        
        wishlist_items = StoreWishlist.objects.filter(store=store, **customer_id)
        products = [item.product for item in wishlist_items]
        
        return Response({
            'products': StoreProductSerializer(products, many=True).data,
            'count': len(products)
        })
    
    @action(detail=False, methods=['post'])
    def add(self, request, store_slug=None):
        """Add a product to the wishlist."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response(
                {'error': 'Authentication required or customer_phone/email needed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        product = get_object_or_404(StoreProduct, id=product_id, store=store, status='active')
        
        wishlist_item, created = StoreWishlist.objects.get_or_create(
            store=store,
            product=product,
            **customer_id
        )
        
        wishlist_count = StoreWishlist.objects.filter(store=store, **customer_id).count()
        
        return Response({
            'message': 'Product added to wishlist',
            'product_id': str(product_id),
            'wishlist_count': wishlist_count
        })
    
    @action(detail=False, methods=['post'])
    def remove(self, request, store_slug=None):
        """Remove a product from the wishlist."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response(
                {'error': 'Authentication required or customer_phone/email needed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        
        StoreWishlist.objects.filter(
            store=store,
            product_id=product_id,
            **customer_id
        ).delete()
        
        wishlist_count = StoreWishlist.objects.filter(store=store, **customer_id).count()
        
        return Response({
            'message': 'Product removed from wishlist',
            'product_id': str(product_id),
            'wishlist_count': wishlist_count
        })
    
    @action(detail=False, methods=['post'])
    def toggle(self, request, store_slug=None):
        """Toggle a product in the wishlist."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response(
                {'error': 'Authentication required or customer_phone/email needed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        product = get_object_or_404(StoreProduct, id=product_id, store=store, status='active')
        
        wishlist_item = StoreWishlist.objects.filter(
            store=store,
            product=product,
            **customer_id
        ).first()
        
        if wishlist_item:
            wishlist_item.delete()
            added = False
        else:
            StoreWishlist.objects.create(
                store=store,
                product=product,
                **customer_id
            )
            added = True
        
        wishlist_count = StoreWishlist.objects.filter(store=store, **customer_id).count()
        
        return Response({
            'message': 'Product added to wishlist' if added else 'Product removed from wishlist',
            'product_id': str(product_id),
            'in_wishlist': added,
            'wishlist_count': wishlist_count
        })
