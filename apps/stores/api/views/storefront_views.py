"""
Storefront API views for public store access.

These views handle cart, checkout, catalog, and wishlist functionality
for the public-facing storefront.
"""
import logging
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse
from django.conf import settings
from django.utils import timezone
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


def _parse_scheduling(data):
    """Retorna (scheduled_date|None, scheduled_time:str) de forma defensiva.
    Nunca levanta — agendamento malformado vira (None, '')."""
    raw_date = (data.get('scheduled_date') or '').strip()
    slot = (data.get('scheduled_time_slot') or '').strip()[:50]
    parsed_date = None
    if raw_date:
        try:
            d = datetime.strptime(raw_date, '%Y-%m-%d').date()
            if d >= timezone.localdate():   # hoje é válido; passado é ignorado
                parsed_date = d
        except (ValueError, TypeError):
            parsed_date = None
    if parsed_date is None:
        slot = ''   # sem data válida, não faz sentido manter o slot
    return parsed_date, slot
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.db import transaction

from apps.core.models import UserProfile
from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import (
    Store, StoreProduct, StoreCategory, StoreCart, StoreCartItem,
    StoreCombo, StoreProductType, StoreCoupon, StoreDeliveryZone,
    StoreCustomer, StorePaymentGateway,
    StoreWishlist, StoreCustomerAddress, StoreOrder,
)
from apps.users.models import UserAddress
from apps.stores.services import cart_service, checkout_service
from apps.stores import billing as billing_service
from apps.stores.services.delivery_quote_service import delivery_quote_service
from apps.stores.services.geo import geo_service
from apps.stores.services.realtime_service import broadcast_order_event
from ..serializers import (
    StoreSerializer, StoreCategorySerializer, StoreProductSerializer,
    StoreCartSerializer, StoreCartItemSerializer, StoreComboSerializer,
    CatalogProductTypeSerializer, StoreWishlistSerializer, WishlistAddRemoveSerializer,
    CheckoutSerializer
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

    addr_records = list(store_customer.address_list.values(
        'id', 'label', 'street', 'number', 'complement', 'neighborhood',
        'city', 'state', 'zip_code', 'reference', 'formatted', 'is_default',
    ))
    for addr in addr_records:
        label = addr.get('label') or ''
        addr['tag'] = label
        addr['name'] = label
        addr['address'] = addr.get('formatted') or addr.get('street') or ''
    default_address = next((a for a in addr_records if a['is_default']), addr_records[0] if addr_records else None)
    default_index = 0

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
        'addresses': addr_records,
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
            .select_related('category', 'product_type')
            .prefetch_related('variants')
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

        combos = StoreCombo.objects.filter(store=store, is_active=True) \
            .prefetch_related(
                'groups__product',
                'groups__variant_limits__variant__product',
                'groups__product_options__product',
            ) \
            .order_by('sort_order', 'name')
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


def _loyalty_program_payload(store):
    meta = store.metadata or {}
    return {
        'enabled': bool(meta.get('loyalty_enabled', True)),
        'threshold': max(1, int(meta.get('loyalty_salads_required', 10) or 10)),
    }


def _featured_coupon_payload(store):
    from apps.stores import billing
    from apps.stores.models import StoreCoupon
    if not billing.plan_allows(store, 'coupon_banner'):
        return None
    coupon = (StoreCoupon.objects
              .filter(store=store, is_active=True, is_featured=True)
              .order_by('-created_at').first())
    if not coupon:
        return None
    ok, _reason = coupon.is_valid()
    if not ok:
        return None
    return {
        'code': coupon.code,
        'description': coupon.description,
        'discount_type': coupon.discount_type,
        'discount_value': str(coupon.discount_value),
        'first_order_only': coupon.first_order_only,
    }


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
            'loyalty_program': _loyalty_program_payload(store),
            'featured_coupon': _featured_coupon_payload(store),
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
                requested_default = data.get('default_address_index', 0)
                try:
                    requested_default = int(requested_default)
                except (TypeError, ValueError):
                    requested_default = 0

                normalized_addresses = []
                for addr_dict in addresses:
                    if not isinstance(addr_dict, dict):
                        continue
                    formatted = addr_dict.get('formatted') or addr_dict.get('address') or ''
                    if not formatted:
                        parts = [
                            addr_dict.get('street', ''), addr_dict.get('number', ''),
                            addr_dict.get('neighborhood', ''), addr_dict.get('city', ''),
                        ]
                        formatted = ', '.join(p for p in parts if p)
                    if not formatted and not any([
                        addr_dict.get('street'), addr_dict.get('address'), addr_dict.get('title'),
                        addr_dict.get('number'), addr_dict.get('city'),
                    ]):
                        continue  # skip entirely-blank address dicts

                    normalized_addresses.append({
                        'label': addr_dict.get('label') or addr_dict.get('tag') or addr_dict.get('name') or '',
                        'street': addr_dict.get('street') or addr_dict.get('address') or addr_dict.get('title') or formatted,
                        'number': addr_dict.get('number', ''),
                        'complement': addr_dict.get('complement', ''),
                        'neighborhood': addr_dict.get('neighborhood', ''),
                        'city': addr_dict.get('city', ''),
                        'state': addr_dict.get('state') or addr_dict.get('state_code') or '',
                        'zip_code': addr_dict.get('zip_code') or addr_dict.get('postal_code') or '',
                        'reference': addr_dict.get('reference', ''),
                        'formatted': formatted,
                    })

                store_customer.address_list.all().delete()
                if normalized_addresses:
                    default_index = min(
                        max(requested_default, 0),
                        len(normalized_addresses) - 1,
                    )
                    for i, addr_dict in enumerate(normalized_addresses):
                        StoreCustomerAddress.objects.create(
                            customer=store_customer,
                            is_default=(i == default_index),
                            **addr_dict,
                        )
                    store_customer.default_address_index = default_index
                else:
                    store_customer.default_address_index = 0
            elif 'default_address_index' in data:
                try:
                    default_index = int(data.get('default_address_index', 0))
                except (TypeError, ValueError):
                    default_index = 0
                current_addresses = list(store_customer.address_list.all())
                if current_addresses:
                    default_index = min(max(default_index, 0), len(current_addresses) - 1)
                    current_addresses[default_index].set_as_default()
                    store_customer.default_address_index = default_index
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
        return self.refetch_with_prefetch(cart)

    def refetch_with_prefetch(self, cart):
        """Reload a cart with the relations the serializer touches, so the
        response serialization is O(1) em queries (itens e combos)."""
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
        try:
            quantity = int(request.data.get('quantity', 1))
            if quantity < 1:
                raise ValueError()
        except (TypeError, ValueError):
            return Response(
                {'error': 'quantity must be a positive integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
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
                group_selections = (
                    request.data.get('group_selections')
                    or request.data.get('selections')
                    or customizations.get('group_selections')
                    or customizations.get('selections')
                    or {}
                )
                combo = StoreCombo.objects.get(id=combo_id, store=store, is_active=True)
                cart_service.add_combo(
                    cart,
                    combo,
                    quantity,
                    customizations=customizations,
                    notes=notes,
                    group_selections=group_selections,
                )
            else:
                # Product
                variant_id = request.data.get('variant_id')
                options = request.data.get('options', {})
                cart_service.add_item(cart, product_id, quantity, variant_id, options, notes)

            return Response(StoreCartSerializer(self.refetch_with_prefetch(cart)).data)
        except StoreCombo.DoesNotExist:
            return Response(
                {'error': 'Combo not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}")
            return Response(
                {'error': 'Erro ao adicionar item ao carrinho.'},
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

        return Response(StoreCartSerializer(self.refetch_with_prefetch(cart)).data)
    
    @action(detail=False, methods=['delete'], url_path='item/(?P<item_id>[^/.]+)')
    def remove_item(self, request, store_slug=None, item_id=None):
        """Remove item from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.remove_item(cart, item_id)
        return Response(StoreCartSerializer(self.refetch_with_prefetch(cart)).data)
    
    @action(detail=False, methods=['delete'])
    def clear_cart(self, request, store_slug=None):
        """Clear all items from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.clear_cart(cart)
        return Response(StoreCartSerializer(self.refetch_with_prefetch(cart)).data)


@method_decorator(csrf_exempt, name='dispatch')
class StoreCheckoutView(APIView):
    """Checkout endpoint for creating orders."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [CheckoutThrottle]

    # Aliases de método de pagamento aceitos pelos storefronts.
    _PAYMENT_METHOD_ALIASES = {
        'credit_card': 'card',
        'debit_card': 'card',
        'cartao': 'card',
        'cartão': 'card',
        'dinheiro': 'cash',
    }

    def _extract_customer_data(self, request):
        """Extrai os dados do cliente (checkout_service espera name/email/phone)."""
        return {
            'name': request.data.get('customer_name') or '',
            'email': request.data.get('customer_email') or '',
            'phone': request.data.get('customer_phone') or '',
            'cpf': request.data.get('cpf', ''),
            'accepts_marketing': request.data.get('accepts_marketing'),
        }

    def _extract_delivery_data(self, request, delivery_method):
        """Extrai os dados de entrega do payload."""
        return {
            'method': delivery_method,
            'address': request.data.get('delivery_address', {}),
            'notes': request.data.get('delivery_notes', ''),
            'zip_code': request.data.get('delivery_zip_code'),
            'lat': request.data.get('lat') or request.data.get('delivery_lat'),
            'lng': request.data.get('lng') or request.data.get('delivery_lng'),
            'fee': request.data.get('delivery_fee'),
            'distance_km': request.data.get('delivery_distance_km'),
            'duration_minutes': request.data.get('delivery_duration_minutes'),
        }

    def _resolve_payment_method(self, raw_payment_method):
        """Resolve o método de pagamento a partir do alias (default 'pix')."""
        return self._PAYMENT_METHOD_ALIASES.get(
            raw_payment_method, raw_payment_method) or 'pix'

    def _build_payment_payload(self, request):
        """Monta o payload de pagamento, injetando a base de redirect da origem."""
        payment_payload = dict(request.data.get('payment', {}) or {})
        request_origin_base = get_request_origin_base(request)
        if request_origin_base:
            payment_payload['redirect_base_url'] = request_origin_base
        return payment_payload

    def _persist_customer_session(self, request, order):
        """Persiste os dados do cliente na sessão para o próximo checkout."""
        request.session['customer_name'] = order.customer_name or ''
        request.session['customer_email'] = order.customer_email or ''
        request.session['customer_phone'] = order.customer_phone or ''
        request.session.modified = True

    def _maybe_send_meta_purchase(self, request, order, payment_result):
        """Envia Purchase imediato apenas para pagamento realmente aprovado.

        PIX/links pendentes são enviados pelo webhook quando virarem PAID; emitir
        na criação do pedido inflaria vendas e impediria o envio correto depois.
        """
        if not payment_result or payment_result.get('status') != 'approved':
            return
        try:
            from apps.stores.services.meta_pixel_service import _get_client_ip
            from apps.stores.tasks import send_meta_purchase_event
            raw = request.data.get('meta')
            meta_tracking = dict(raw) if isinstance(raw, dict) else {}
            # Pré-extrai os dados derivados do request (não-serializável p/ Celery),
            # replicando o que send_purchase_event lia do request.
            meta_tracking.setdefault('client_ip', _get_client_ip(request))
            meta_tracking.setdefault('user_agent', request.META.get('HTTP_USER_AGENT', ''))
            if not meta_tracking.get('event_source_url'):
                meta_tracking['event_source_url'] = (
                    request.headers.get('Referer') or request.headers.get('Origin') or ''
                )
            # Envio assíncrono: tira o requests.post(timeout=3) do caminho do response.
            transaction.on_commit(
                lambda: send_meta_purchase_event.delay(str(order.id), meta_tracking)
            )
        except Exception as exc:
            logger.warning("Meta CAPI Purchase enqueue failed for %s: %s", order.order_number, exc)

    def _serialize_order_item(self, item):
        """Serializa um item do pedido para a resposta de checkout."""
        return {
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

    def _build_response_data(self, store, order):
        """Monta o corpo base da resposta de checkout (sem dados de pagamento)."""
        return {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'total': str(order.total),
            'total_amount': float(order.total),
            'payment_status': order.payment_status,
            'access_token': order.access_token,
            'items': [self._serialize_order_item(item) for item in order.items.all()],
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

    def _apply_payment_result(self, response_data, payment_result, payment_method):
        """Acrescenta os dados de pagamento (sucesso ou erro) à resposta."""
        if not payment_result:
            return
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
            response_data['pix_expiration'] = payment_result.get('expiration', '')
            response_data['init_point'] = payment_result.get('init_point', '')
            response_data['sandbox_init_point'] = payment_result.get('sandbox_init_point', '')
        else:
            response_data['payment_error'] = payment_result.get('error', 'Erro no pagamento')
            # Corpo honesto: a cobrança NÃO foi criada — não pode fingir
            # 'pending' (o service já marcou o pedido como FAILED no banco).
            response_data['payment_status'] = StoreOrder.PaymentStatus.FAILED

    def post(self, request, store_slug):
        """Process checkout and create order."""
        store = get_active_store(store_slug)

        if not billing_service.store_accepts_orders(store):
            return Response(
                {'detail': 'Loja temporariamente indisponível.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Limite de pedidos/mês (plano Grátis). Isento e planos ilimitados passam.
        # SSOT da contagem: billing.orders_in_current_month (range indexável,
        # semântica de mês em fuso local — ver docstring).
        _month_count = billing_service.orders_in_current_month(store)
        if not billing_service.within_order_limit(store, _month_count):
            return Response(
                {'detail': 'Limite do plano atingido (30 pedidos/mês). Faça upgrade do plano.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get cart
        session_id = get_request_cart_key(request)
        user = request.user if request.user.is_authenticated else None
        cart = cart_service.get_or_create_cart(store, user, session_id)

        if not cart.items.exists() and not cart.combo_items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )

        customer_data = self._extract_customer_data(request)

        delivery_method = request.data.get('delivery_method') or request.data.get('shipping_method') or 'delivery'
        delivery_data = self._extract_delivery_data(request, delivery_method)

        coupon_code = request.data.get('coupon_code', '')
        notes = request.data.get('customer_notes') or request.data.get('notes', '')
        raw_payment_method = (request.data.get('payment_method') or '').strip()
        payment_requested = bool(raw_payment_method)
        payment_method = self._resolve_payment_method(raw_payment_method)
        payment_payload = self._build_payment_payload(request)

        # Validate checkout data
        checkout_data = {
            'customer_name': customer_data['name'],
            'customer_email': customer_data['email'],
            'customer_phone': customer_data['phone'],
            'delivery_method': delivery_method,
            'payment_method': payment_method,
        }
        checkout_serializer = CheckoutSerializer(data=checkout_data)
        if not checkout_serializer.is_valid():
            logger.error(f'Checkout validation failed: {checkout_serializer.errors}')
            return Response(
                {'error': 'Dados de checkout inválidos', 'details': checkout_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        scheduled_date, scheduled_time = _parse_scheduling(request.data)
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
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time,
            )

            self._persist_customer_session(request, order)

            # Process payment if method specified
            payment_result = None
            if payment_requested:
                payment_result = checkout_service.create_payment(
                    order, payment_method, payment_payload
                )

            self._maybe_send_meta_purchase(request, order, payment_result)

            # Dispara o broadcast após o commit, fora do caminho do response.
            # Fora de um bloco atomic o Django executa o callback imediatamente,
            # então o comportamento é idêntico (uma vez por pedido criado).
            transaction.on_commit(
                lambda: broadcast_order_event(order, event_type='order.created')
            )

            # Clear cart after successful order
            cart_service.clear_cart(cart)

            response_data = self._build_response_data(store, order)
            self._apply_payment_result(response_data, payment_result, payment_method)

            return Response(response_data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Checkout error: {e}")
            return Response(
                {'error': 'Erro ao processar checkout.'},
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

        if not (lat and lng) and not address and not zip_code:
            if distance_km is not None:
                try:
                    delivery_info = delivery_quote_service.calculate_for_distance(
                        store,
                        distance_km=Decimal(str(distance_km)),
                        zip_code=zip_code,
                    )
                    return Response(delivery_quote_service.normalize(delivery_info))
                except Exception as e:
                    logger.error(f"Delivery fee calculation error: {e}")
                    return Response(
                        {'error': 'Erro ao calcular taxa de entrega.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
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

            from apps.stores.services.unified_delivery_service import UnifiedDeliveryService

            delivery_info = UnifiedDeliveryService.calculate_delivery_fee(
                store=store,
                delivery_method='delivery',
                lat=float(lat) if lat else None,
                lng=float(lng) if lng else None,
                address_text=address or zip_code or None,
            )
            return Response(delivery_quote_service.normalize(delivery_info))
        except Exception as e:
            logger.error(f"Delivery fee calculation error: {e}")
            return Response(
                {'error': 'Erro ao calcular taxa de entrega.'},
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
            
            # Check validity (includes min_purchase check). Guest é identificado
            # pelo telefone quando o front manda — sem isso limites por cliente
            # e "primeira compra" não valem pra checkout sem login.
            valid, error_msg = coupon.is_valid(
                subtotal=subtotal,
                user=request.user,
                customer_phone=(request.data.get('customer_phone') or '').strip() or None,
            )
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
        
        # select_related/prefetch espelham o catálogo: evita N+1 de product +
        # category/product_type/variants ao serializar a wishlist.
        wishlist_items = (
            StoreWishlist.objects.filter(store=store, **customer_id)
            .select_related('product', 'product__category', 'product__product_type')
            .prefetch_related('product__variants')
        )
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


class MyAddressViewSet(viewsets.ModelViewSet):
    """CRUD de endereços salvos do cliente logado."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None  # set in __init__
    lookup_field = 'id'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.users.serializers import UserAddressSerializer
        self.serializer_class = UserAddressSerializer

    def get_store_slug(self):
        """Extract store slug from request path or kwargs."""
        # When used via include(store_frontend_patterns), Django injects store_slug into kwargs
        if 'store_slug' in self.kwargs:
            return self.kwargs['store_slug']

        # Fallback: extract from URL path
        path_parts = self.request.path.split('/')
        if len(path_parts) > 4 and path_parts[3]:
            return path_parts[3]

        return None

    def get_store(self):
        """Get store by slug from request."""
        store_slug = self.get_store_slug()
        if not store_slug:
            raise get_object_or_404(Store, slug=None)
        return get_object_or_404(Store, slug=store_slug)

    def get_queryset(self):
        """Retorna endereços do usuário logado para a loja atual."""
        store = self.get_store()

        # Filtrar por unified_user (do token) + tenant (loja)
        unified_user = getattr(self.request.user, 'unified_user', None)
        if not unified_user:
            # Fallback se user não tiver unified_user populado
            from apps.users.models import UnifiedUser
            unified_user = UnifiedUser.objects.filter(user=self.request.user).first()

        if not unified_user:
            return UserAddress.objects.none()

        return UserAddress.objects.filter(
            unified_user=unified_user,
            tenant=store
        ).order_by('-is_default', '-created_at')

    def perform_create(self, serializer):
        """Criar endereço vinculando ao usuário e loja."""
        store = self.get_store()

        unified_user = getattr(self.request.user, 'unified_user', None)
        if not unified_user:
            from apps.users.models import UnifiedUser
            unified_user = UnifiedUser.objects.filter(user=self.request.user).first()

        serializer.save(unified_user=unified_user, tenant=store)

    @action(detail=True, methods=['patch'])
    def set_default(self, request, *args, **kwargs):
        """Marcar endereço como padrão."""
        address = self.get_object()

        # Desmarcar outros como padrão para o mesmo usuário/loja
        UserAddress.objects.filter(
            unified_user=address.unified_user,
            tenant=address.tenant,
            is_default=True
        ).exclude(id=address.id).update(is_default=False)

        # Marcar este como padrão
        address.is_default = True
        address.save(update_fields=['is_default', 'updated_at'])

        serializer = self.get_serializer(address)
        return Response(serializer.data)
