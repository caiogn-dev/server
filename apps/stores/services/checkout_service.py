"""
Checkout Service - Unified checkout for all stores.
Handles order creation, payment processing, and stock management.
"""
import logging
import re
import uuid
from decimal import Decimal
from urllib.parse import urlparse
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import (
    Store, StoreCart, StoreOrder, StoreOrderItem, StoreOrderComboItem,
    StoreProduct, StoreProductVariant, StoreIntegration,
    StoreDeliveryZone, StoreCoupon
)
from .cart_service import cart_service

logger = logging.getLogger(__name__)


def _normalize_address_text(value: str) -> str:
    if not value:
        return ''
    import unicodedata
    normalized = unicodedata.normalize('NFD', str(value).lower())
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^a-z0-9\s]', ' ', normalized)


def _extract_quadra_numbers(value: str) -> set[str]:
    text = _normalize_address_text(value)
    numbers = set()
    patterns = [
        r'\bq(?:uadra)?\s*\.?\s*(\d{2,4})\s*(?:sul|norte)?\b',
        r'\b(\d{2,4})\s*(?:sul|norte)\b',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            quadra = str(match).lstrip('0')
            if quadra:
                numbers.add(quadra)
    return numbers


def _sanitize_delivery_address_coordinates(delivery_address: dict) -> dict:
    """
    Drop stale coordinates/raw geocode data when the typed address conflicts
    with the reverse-geocoded label. Prevents "203 Sul" orders carrying a
    persisted Maps pin/raw address for "912 Sul".
    """
    if not isinstance(delivery_address, dict):
        return delivery_address

    raw_address = (
        delivery_address.get('raw_address')
        or delivery_address.get('formatted_address')
        or delivery_address.get('display_name')
    )
    if not raw_address:
        return delivery_address

    typed_address = ' '.join(
        str(delivery_address.get(key) or '')
        for key in ('street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code')
    )
    typed_quadra = _extract_quadra_numbers(typed_address)
    raw_quadra = _extract_quadra_numbers(raw_address)

    if not typed_quadra or not raw_quadra or typed_quadra & raw_quadra:
        return delivery_address

    sanitized = dict(delivery_address)
    for key in ('lat', 'lng', 'latitude', 'longitude', 'formatted_address', 'display_name'):
        sanitized.pop(key, None)
    sanitized['raw_address'] = ', '.join(
        part for part in [
            sanitized.get('street'),
            sanitized.get('number'),
            sanitized.get('complement'),
            sanitized.get('neighborhood'),
            sanitized.get('city'),
            sanitized.get('state'),
            sanitized.get('zip_code'),
        ]
        if part
    )
    logger.warning(
        "Sanitized conflicting delivery geocode: typed_quadra=%s raw_quadra=%s raw_address=%s",
        sorted(typed_quadra),
        sorted(raw_quadra),
        raw_address,
    )
    return sanitized


def get_valid_email_for_payment(order: StoreOrder) -> str:
    """
    Get a valid email for payment processing.
    Mercado Pago doesn't accept emails with .local domains.
    """
    email = order.customer_email
    
    # Check if email is valid for Mercado Pago
    # Reject .local domains and obvious invalid emails
    if email and re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        domain = email.split('@')[-1].lower()
        if not domain.endswith('.local') and not domain.endswith('.test'):
            return email
    
    # Try to get email from store owner
    if order.store and order.store.owner and order.store.owner.email:
        return order.store.owner.email
    
    # Fallback to a noreply address using the store's domain if available
    store_domain = 'noreply.com'
    if order.store and getattr(order.store, 'website_url', ''):
        from urllib.parse import urlparse
        parsed = urlparse(order.store.website_url)
        if parsed.netloc:
            store_domain = parsed.netloc
    return f"cliente@{store_domain}"


def trigger_order_email_automation(order: StoreOrder, trigger_type: str, extra_context: dict = None):
    """Trigger email automation for order events."""
    try:
        from apps.marketing.services.email_automation_service import email_automation_service
        
        if not order.customer_email:
            logger.debug(f"No customer email for order {order.order_number}, skipping automation")
            return
        
        store_id = str(order.store.id) if order.store else None
        if not store_id:
            logger.debug(f"No store for order {order.order_number}, skipping automation")
            return
        
        context = {
            'order_number': order.order_number,
            'order_total': f'{order.total:.2f}',
            'order_status': order.status,
            'delivery_method': order.delivery_method,
            **(extra_context or {})
        }
        
        result = email_automation_service.trigger(
            store_id=store_id,
            trigger_type=trigger_type,
            recipient_email=order.customer_email,
            recipient_name=order.customer_name or '',
            context=context
        )
        logger.info(f"Email automation triggered for order {order.order_number}: {trigger_type} -> {result}")
        
    except Exception as e:
        logger.error(f"Failed to trigger email automation for order {order.order_number}: {e}")


class CheckoutService:
    """Service for processing checkouts."""

    @staticmethod
    def _normalize_base_url(raw_url: str) -> str:
        """Return scheme + host only for a storefront or app deep link base URL."""
        if not raw_url:
            return ''

        candidate = str(raw_url).strip()
        if not candidate:
            return ''

        if candidate.startswith('//'):
            candidate = f'https:{candidate}'
        elif not re.match(r'^[a-z][a-z0-9+.-]*://', candidate, re.IGNORECASE):
            candidate = f'https://{candidate}'

        parsed = urlparse(candidate)
        if not parsed.scheme or not parsed.netloc:
            return ''

        return f'{parsed.scheme}://{parsed.netloc}'

    @staticmethod
    def get_storefront_base_url(store: Store, payment_payload: dict = None) -> str:
        """
        Resolve the correct storefront base URL for post-payment redirects.

        Priority:
        1. Explicit redirect URL passed by the current storefront request
        2. Store metadata URLs
        3. Linked automation profile URLs
        4. Global FRONTEND_URL fallback
        """
        candidates = []
        payload = payment_payload or {}

        for key in ('redirect_base_url', '_redirect_base_url', 'frontend_url', 'storefront_url'):
            value = payload.get(key)
            if value:
                candidates.append(value)

        metadata = getattr(store, 'metadata', {}) or {}
        for key in ('frontend_url', 'website_url', 'storefront_url', 'order_url', 'menu_url'):
            value = metadata.get(key)
            if value:
                candidates.append(value)

        automation_profile = getattr(store, 'automation_profile', None)
        if automation_profile:
            for attr_name in ('order_url', 'menu_url', 'website_url'):
                value = getattr(automation_profile, attr_name, '')
                if value:
                    candidates.append(value)

        candidates.append(getattr(settings, 'FRONTEND_URL', ''))

        for candidate in candidates:
            normalized = CheckoutService._normalize_base_url(candidate)
            if normalized:
                return normalized.rstrip('/')

        return 'http://localhost:3000'
    
    @staticmethod
    def calculate_delivery_fee(store: Store, distance_km: Decimal = None, zip_code: str = None) -> dict:
        """Calculate delivery fee based on distance.
        
        Uses dynamic distance-based calculation for consistent pricing.
        Configured zones are only used if they have proper min_km/max_km ranges.
        """
        if distance_km is not None:
            logger.info(f"Calculating delivery fee for distance: {distance_km} km")
            
            # Check for properly configured distance zones with explicit ranges
            zones = StoreDeliveryZone.objects.filter(
                store=store,
                is_active=True,
                zone_type='custom_distance',
                min_km__isnull=False,
                max_km__isnull=False
            ).order_by('min_km')
            
            # Only use zones that have explicit min/max km configured
            for zone in zones:
                if zone.min_km <= distance_km < zone.max_km:
                    fee = zone.delivery_fee
                    if zone.fee_per_km:
                        fee += zone.fee_per_km * distance_km
                    logger.info(f"Using configured zone '{zone.name}': R${fee}")
                    return {
                        'fee': float(fee),
                        'delivery_fee': float(fee),
                        'is_valid': True,
                        'available': True,
                        'zone_id': str(zone.id),
                        'zone_name': zone.name,
                        'estimated_minutes': zone.estimated_minutes,
                        'estimated_days': zone.estimated_days,
                        'distance_km': float(distance_km),
                    }
            
            # No matching zone - use dynamic calculation
            logger.info(f"No matching zone found, using dynamic calculation")
            return CheckoutService._calculate_dynamic_fee(store, distance_km)
        
        # No distance provided - return base fee
        return CheckoutService._calculate_dynamic_fee(store, None)
    
    @staticmethod
    def _calculate_dynamic_fee(store: Store, distance_km: Decimal = None) -> dict:
        """Calculate delivery fee dynamically based on distance.

        Default pricing (Ce Saladas):
          - R$ 9,00 flat até 4 km
          - R$ 9,00 + (dist - 4) × R$ 1,00 acima de 4 km
          - Acima de 16 km: fee=None (a combinar)

        Overridable via store.metadata keys:
          delivery_base_fee      (default 9.00)
          delivery_fee_per_km    (default 1.00)
          delivery_flat_km       (default 4.0 — distância onde a taxa é plana)
          delivery_free_km       (legacy alias for delivery_flat_km)
          delivery_max_km        (default 16.0 — acima disso retorna fee=None)
          delivery_max_fee       (optional legacy cap; when present, caps fee instead of out-of-range)
        """
        metadata = store.metadata or {}
        base_fee = Decimal(str(metadata.get('delivery_base_fee', store.default_delivery_fee or '9.00')))
        fee_per_km = Decimal(str(metadata.get('delivery_fee_per_km', '1.00')))
        flat_km = Decimal(str(metadata.get('delivery_flat_km') or metadata.get('delivery_free_km') or '4.0'))
        max_km_raw = metadata.get('delivery_max_km') or metadata.get('max_delivery_distance_km')
        max_km = Decimal(str(max_km_raw)) if max_km_raw is not None else Decimal('16.0')
        max_fee_raw = metadata.get('delivery_max_fee')
        max_fee = Decimal(str(max_fee_raw)) if max_fee_raw not in (None, '') else None

        if distance_km is None:
            return {
                'fee': float(base_fee),
                'delivery_fee': float(base_fee),
                'is_valid': True,
                'available': True,
                'zone_name': 'Padrão',
                'estimated_minutes': 30,
                'estimated_days': 0,
                'distance_km': None,
                'calculation': 'dynamic',
            }

        distance = Decimal(str(distance_km))

        # Acima do limite máximo → a combinar
        if max_fee is None and distance > max_km:
            return {
                'fee': None,
                'delivery_fee': None,
                'is_valid': False,
                'available': False,
                'zone_name': 'Fora da área',
                'estimated_minutes': None,
                'estimated_days': 0,
                'distance_km': float(distance),
                'calculation': 'out_of_range',
                'reason': 'out_of_range',
                'message': 'Distância acima de 16 km — entrar em contato para combinar frete',
            }

        if distance <= flat_km:
            fee = base_fee
            zone_name = 'Próximo'
        else:
            extra_km = distance - flat_km
            fee = base_fee + (extra_km * fee_per_km)
            if distance <= 8:
                zone_name = 'Padrão'
            elif distance <= 12:
                zone_name = 'Distante'
            else:
                zone_name = 'Remoto'

        if max_fee is not None:
            fee = min(fee, max_fee)

        fee = fee.quantize(Decimal('0.01'))
        estimated_minutes = int(15 + (float(distance) * 3))

        return {
            'fee': float(fee),
            'delivery_fee': float(fee),
            'is_valid': True,
            'available': True,
            'zone_name': zone_name,
            'estimated_minutes': estimated_minutes,
            'estimated_days': 0,
            'distance_km': float(distance),
            'calculation': 'dynamic',
        }

    @staticmethod
    def normalize_delivery_quote(info: dict, route: dict = None) -> dict:
        """Return a stable delivery quote while preserving legacy response keys."""
        payload = dict(info or {})
        route_payload = dict(route or {})

        fee = payload.get('fee', payload.get('delivery_fee'))
        is_valid = payload.get('is_valid')
        if is_valid is None:
            is_valid = payload.get('available')
        if is_valid is None:
            is_valid = payload.get('is_within_area')
        if is_valid is None:
            is_valid = fee is not None

        zone = payload.get('zone') if isinstance(payload.get('zone'), dict) else {}
        zone_name = (
            payload.get('zone_name')
            or payload.get('delivery_zone')
            or zone.get('name')
        )
        distance_km = payload.get('distance_km', route_payload.get('distance_km'))
        duration_minutes = payload.get('duration_minutes', route_payload.get('duration_minutes'))
        estimated_minutes = payload.get('estimated_minutes') or duration_minutes
        reason = payload.get('reason') or (None if is_valid else payload.get('calculation') or 'unavailable')

        stable = {
            'is_valid': bool(is_valid),
            'valid': bool(is_valid),
            'available': bool(is_valid),
            'fee': fee,
            'delivery_fee': fee,
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'estimated_minutes': estimated_minutes,
            'zone_name': zone_name,
            'delivery_zone': zone_name,
            'zone': zone or ({'name': zone_name} if zone_name else None),
            'message': payload.get('message') or ('Entrega disponível' if is_valid else 'Entrega indisponível'),
            'reason': reason,
            'calculation': payload.get('calculation'),
            'polyline': payload.get('polyline') or route_payload.get('polyline'),
            'provider': payload.get('provider') or route_payload.get('provider'),
            'rain_surcharge_applied': bool(payload.get('rain_surcharge_applied', False)),
        }
        payload.update({k: v for k, v in stable.items() if v is not None})
        return payload

    @staticmethod
    def normalize_custom_salad_payload(customizations: dict, combo_name: str, unit_price=None) -> dict:
        """Validate and normalize mobile salad-builder customizations."""
        data = dict(customizations or {})
        ingredients_raw = data.get('ingredients') or []
        if isinstance(ingredients_raw, str):
            ingredients = [part.strip() for part in ingredients_raw.split('·') if part.strip()]
        elif isinstance(ingredients_raw, list):
            ingredients = [str(part).strip() for part in ingredients_raw if str(part).strip()]
        else:
            ingredients = []

        custom_name = str(data.get('custom_name') or combo_name or 'Monte sua Salada').strip()
        if not ingredients:
            raise ValueError('Salada personalizada precisa informar ingredientes')

        normalized = {
            **data,
            'type': 'custom_salad',
            'is_salad_builder': True,
            'custom_name': custom_name,
            'ingredients': ingredients,
        }
        if unit_price is not None:
            normalized['unit_price'] = str(unit_price)
        if 'total_price' not in normalized and unit_price is not None:
            normalized['total_price'] = str(unit_price)
        return normalized

    @staticmethod
    def _is_salad_order_item(item: StoreOrderItem) -> bool:
        text_parts = [item.product_name or '', item.variant_name or '']
        if item.product:
            text_parts.extend([
                getattr(item.product.category, 'name', '') if item.product.category else '',
                getattr(item.product.category, 'slug', '') if item.product.category else '',
                getattr(item.product.product_type, 'name', '') if item.product.product_type else '',
                getattr(item.product.product_type, 'slug', '') if item.product.product_type else '',
            ])
        options = item.options if isinstance(item.options, dict) else {}
        if options.get('is_salad_builder') or options.get('type') == 'custom_salad':
            return True
        blob = ' '.join(text_parts).lower()
        return 'salada' in blob or 'salad' in blob

    @staticmethod
    def _is_salad_cart_item(item) -> bool:
        product = getattr(item, 'product', None)
        if product:
            blob = ' '.join([
                getattr(product, 'name', '') or '',
                getattr(getattr(product, 'category', None), 'name', '') or '',
                getattr(getattr(product, 'category', None), 'slug', '') or '',
                getattr(getattr(product, 'product_type', None), 'name', '') or '',
                getattr(getattr(product, 'product_type', None), 'slug', '') or '',
            ]).lower()
            return 'salada' in blob or 'salad' in blob
        customizations = getattr(item, 'customizations', {}) or {}
        return bool(customizations.get('is_salad_builder') or customizations.get('type') == 'custom_salad')

    @staticmethod
    def get_loyalty_status(store: Store, user=None) -> dict:
        threshold = int((store.metadata or {}).get('loyalty_salads_required', 10) or 10)
        threshold = max(1, threshold)
        enabled = bool((store.metadata or {}).get('loyalty_enabled', True))

        if not user or not getattr(user, 'is_authenticated', False):
            return {
                'enabled': enabled,
                'threshold': threshold,
                'qualified_salads': 0,
                'rewards_earned': 0,
                'rewards_redeemed': 0,
                'available_rewards': 0,
                'progress': 0,
                'remaining': threshold,
                'can_redeem': False,
            }

        orders = (
            StoreOrder.objects
            .filter(store=store, customer=user)
            .exclude(status__in=[
                StoreOrder.OrderStatus.CANCELLED,
                StoreOrder.OrderStatus.FAILED,
                StoreOrder.OrderStatus.REFUNDED,
            ])
            .filter(Q(payment_status=StoreOrder.PaymentStatus.PAID) | Q(status__in=[
                StoreOrder.OrderStatus.PAID,
                StoreOrder.OrderStatus.DELIVERED,
                StoreOrder.OrderStatus.COMPLETED,
            ]))
            .prefetch_related('items__product__category', 'items__product__product_type')
        )

        qualified = 0
        redeemed = 0
        for order in orders:
            loyalty_meta = (order.metadata or {}).get('loyalty_reward') or {}
            if loyalty_meta.get('applied'):
                redeemed += int(loyalty_meta.get('count') or 1)
            for item in order.items.all():
                if CheckoutService._is_salad_order_item(item):
                    qualified += int(item.quantity or 0)

        earned = qualified // threshold
        available = max(0, earned - redeemed)
        progress = qualified % threshold
        return {
            'enabled': enabled,
            'threshold': threshold,
            'qualified_salads': qualified,
            'rewards_earned': earned,
            'rewards_redeemed': redeemed,
            'available_rewards': available,
            'progress': progress,
            'remaining': 0 if available else max(0, threshold - progress),
            'can_redeem': enabled and available > 0,
            'label': f'A cada {threshold} saladas, 1 grátis',
        }

    @staticmethod
    def _cart_salad_discount(cart: StoreCart) -> Decimal:
        prices = []
        for item in cart.items.select_related('product__category', 'product__product_type', 'variant').all():
            if CheckoutService._is_salad_cart_item(item):
                prices.extend([Decimal(str(item.unit_price))] * int(item.quantity or 0))
        for item in cart.combo_items.all():
            if CheckoutService._is_salad_cart_item(item):
                prices.extend([Decimal(str(item.effective_price))] * int(item.quantity or 0))
        return min(prices) if prices else Decimal('0')
    
    @staticmethod
    def validate_coupon(store: Store, code: str, subtotal: Decimal, user=None) -> dict:
        """Validate a coupon code for a store using the unified StoreCoupon model."""
        try:
            # Find coupon for this store
            coupon = StoreCoupon.objects.filter(
                store=store,
                code__iexact=code,
                is_active=True
            ).first()
            
            if not coupon:
                return {'valid': False, 'error': 'Cupom nao encontrado'}
            
            # Use the model's is_valid method which handles all validation
            is_valid, error_message = coupon.is_valid(subtotal=subtotal, user=user)
            if not is_valid:
                return {'valid': False, 'error': error_message}
            
            discount = coupon.calculate_discount(subtotal)
            
            return {
                'valid': True,
                'coupon_id': str(coupon.id),
                'code': coupon.code,
                'discount': float(discount),
                'discount_type': coupon.discount_type,
                'discount_value': float(coupon.discount_value),
            }
        
        except Exception as e:
            logger.error(f"Coupon validation error: {e}")
            return {'valid': False, 'error': 'Erro ao validar cupom'}
    
    @staticmethod
    def calculate_totals(
        cart: StoreCart,
        delivery_fee: Decimal = Decimal('0'),
        discount: Decimal = Decimal('0')
    ) -> dict:
        """Calculate order totals."""
        subtotal = Decimal(str(cart.subtotal))
        
        # Add combo items
        for combo_item in cart.combo_items.all():
            subtotal += combo_item.subtotal
        
        # Total = subtotal + delivery - discount (no tax)
        total = subtotal + delivery_fee - discount
        
        return {
            'subtotal': float(subtotal),
            'delivery_fee': float(delivery_fee),
            'tax': 0,
            'discount': float(discount),
            'total': float(max(total, Decimal('0'))),
        }
    
    @staticmethod
    @transaction.atomic
    def create_order(
        cart: StoreCart,
        customer_data: dict,
        delivery_data: dict = None,
        coupon_code: str = None,
        notes: str = '',
        use_loyalty_reward: bool = False,
    ) -> StoreOrder:
        """
        Create an order from a cart with atomic stock decrement.
        """
        store = cart.store
        delivery_payload = dict(delivery_data or {})
        delivery_address = dict(delivery_payload.get('address') or {})
        delivery_address = _sanitize_delivery_address_coordinates(delivery_address)
        delivery_payload['address'] = delivery_address

        if delivery_payload.get('method') == 'delivery':
            if store.city and not delivery_address.get('city'):
                delivery_address['city'] = store.city
            if store.state and not delivery_address.get('state'):
                delivery_address['state'] = store.state
            delivery_payload['address'] = delivery_address

        # Validate stock
        stock_errors = cart_service.validate_stock_for_checkout(cart)
        if stock_errors:
            raise ValueError(f"Erros de estoque: {stock_errors}")
        
        # Calculate delivery fee
        delivery_info = CheckoutService.normalize_delivery_quote({
            'fee': 0.0,
            'delivery_fee': 0.0,
            'zone_name': 'Retirada',
            'is_valid': True,
            'available': True,
        })
        if delivery_payload and delivery_payload.get('method') == 'delivery':
            distance = delivery_payload.get('distance_km')
            zip_code = delivery_payload.get('zip_code')
            delivery_info = CheckoutService.calculate_delivery_fee(
                store,
                distance_km=Decimal(str(distance)) if distance else None,
                zip_code=zip_code
            )
            delivery_info = CheckoutService.normalize_delivery_quote(delivery_info)
        
        if delivery_info.get('fee') is None:
            raise ValueError(delivery_info.get('message') or 'Endereço fora da área de entrega')

        delivery_fee = Decimal(str(delivery_info['fee']))
        
        # Calculate subtotal
        subtotal = Decimal('0')
        for item in cart.items.all():
            subtotal += item.subtotal
        for combo_item in cart.combo_items.all():
            subtotal += combo_item.subtotal

        customer_record = CustomerIdentityService.sync_checkout_customer(
            store=store,
            customer_name=customer_data.get('name', ''),
            email=customer_data.get('email', ''),
            phone=customer_data.get('phone', ''),
            cpf=customer_data.get('cpf', ''),
            delivery_method=delivery_payload.get('method', '') if delivery_payload else '',
            delivery_address=delivery_payload.get('address', {}) if delivery_payload else {},
            user=cart.user,
        )
        customer_user = customer_record.get('user')
        store_customer = customer_record.get('store_customer')
        
        # Validate and apply coupon using unified StoreCoupon model
        discount = Decimal('0')
        coupon = None
        if coupon_code:
            coupon_result = CheckoutService.validate_coupon(store, coupon_code, subtotal, user=cart.user)
            if coupon_result['valid']:
                discount = Decimal(str(coupon_result['discount']))
                coupon = StoreCoupon.objects.get(id=coupon_result['coupon_id'])

        loyalty_reward = {
            'applied': False,
            'count': 0,
            'discount': 0.0,
        }
        if use_loyalty_reward:
            loyalty_user = customer_user or cart.user
            loyalty_status = CheckoutService.get_loyalty_status(store, loyalty_user)
            loyalty_discount = CheckoutService._cart_salad_discount(cart)
            if not loyalty_status.get('can_redeem'):
                raise ValueError('Clube Verde ainda não possui salada grátis disponível')
            if loyalty_discount <= 0:
                raise ValueError('Adicione uma salada para usar a salada grátis')
            discount += loyalty_discount
            loyalty_reward = {
                'applied': True,
                'count': 1,
                'discount': float(loyalty_discount),
                'threshold': loyalty_status.get('threshold', 10),
            }
        
        # Calculate total (no tax - just subtotal + delivery - discount)
        total = subtotal + delivery_fee - discount

        # Create order
        order = StoreOrder.objects.create(
            store=store,
            customer=customer_user or cart.user,
            customer_name=customer_data.get('name', ''),
            customer_email=customer_data.get('email', ''),
            customer_phone=customer_data.get('phone', ''),
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            subtotal=subtotal,
            discount=discount,
            coupon_code=coupon_code or '',
            tax=Decimal('0'),
            delivery_fee=delivery_fee,
            total=total,
            delivery_method=(
                StoreOrder.DeliveryMethod.DELIVERY 
                if delivery_payload and delivery_payload.get('method') == 'delivery'
                else StoreOrder.DeliveryMethod.PICKUP
            ),
            delivery_address=delivery_payload.get('address', {}) if delivery_payload else {},
            delivery_notes=delivery_payload.get('notes', '') if delivery_payload else '',
            customer_notes=notes,
            metadata={
                'delivery_zone': delivery_info.get('zone_name'),
                'delivery_quote': delivery_info,
                'estimated_minutes': delivery_info.get('estimated_minutes'),
                'loyalty_reward': loyalty_reward,
                'customer': {
                    'user_id': str(customer_user.id) if customer_user else '',
                    'store_customer_id': str(store_customer.id) if store_customer else '',
                    'cpf': customer_data.get('cpf', '') or '',
                    'auth_channel': 'whatsapp_otp',
                },
            }
        )
        if customer_user and customer_user != cart.user:
            cart.user = customer_user
            cart.save(update_fields=['user', 'updated_at'])
        
        # Create order items and decrement stock
        for item in cart.items.select_related('product', 'variant').all():
            StoreOrderItem.objects.create(
                order=order,
                product=item.product,
                variant=item.variant,
                product_name=item.product.name,
                variant_name=item.variant.name if item.variant else '',
                sku=item.variant.sku if item.variant else item.product.sku,
                unit_price=item.unit_price,
                quantity=item.quantity,
                subtotal=item.subtotal,
                options=item.options,
                notes=item.notes,
            )
            
            # Atomic stock decrement
            if item.product.track_stock:
                if item.variant:
                    StoreProductVariant.objects.filter(id=item.variant.id).update(
                        stock_quantity=F('stock_quantity') - item.quantity
                    )
                else:
                    StoreProduct.objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') - item.quantity,
                        sold_count=F('sold_count') + item.quantity
                    )
        
        # Handle combo items (real and virtual)
        for combo_item in cart.combo_items.select_related('combo').all():
            is_virtual = combo_item.combo is None
            display_name = combo_item.effective_name
            effective_price = combo_item.effective_price

            if not is_virtual:
                display_name = f"Combo: {display_name}"

            StoreOrderItem.objects.create(
                order=order,
                product=None,
                variant=None,
                product_name=display_name,
                variant_name='',
                sku='',
                unit_price=effective_price,
                quantity=combo_item.quantity,
                subtotal=combo_item.subtotal,
                options=combo_item.customizations,
                notes=combo_item.notes,
            )

            # Decrement combo stock if tracked (real combos only)
            if not is_virtual and combo_item.combo.track_stock:
                from apps.stores.models import StoreCombo
                StoreCombo.objects.filter(id=combo_item.combo.id).update(
                    stock_quantity=F('stock_quantity') - combo_item.quantity
                )
        
        # Mark coupon as used (atomic)
        if coupon:
            coupon.increment_usage()

        if store_customer:
            store_customer.last_order_at = timezone.now()
            store_customer.save(update_fields=['last_order_at', 'updated_at'])
        
        # Clear the cart
        cart.clear()
        cart.is_active = False
        cart.save()
        
        logger.info(f"Order {order.order_number} created for store {store.slug}")
        
        # Trigger order received email automation (NOT confirmed - payment pending)
        # The 'order_confirmed' / 'payment_confirmed' email will ONLY be sent
        # after payment is confirmed via webhook
        trigger_order_email_automation(order, 'order_received')
        
        return order
    
    @staticmethod
    def get_payment_credentials(store: Store) -> dict:
        """Get payment credentials for a store."""
        integration = StoreIntegration.objects.filter(
            store=store,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            status=StoreIntegration.IntegrationStatus.ACTIVE
        ).first()
        
        if integration and integration.access_token:
            return {
                'provider': 'mercadopago',
                'access_token': integration.access_token,
                'sandbox': integration.settings.get('sandbox', False),
            }
        
        # Fallback to global credentials
        access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', None)
        if access_token:
            return {
                'provider': 'mercadopago',
                'access_token': access_token,
                'sandbox': getattr(settings, 'MERCADO_PAGO_SANDBOX', False),
            }
        
        return None
    
    @staticmethod
    def create_payment(order: StoreOrder, payment_method: str = 'pix', payment_data: dict = None) -> dict:
        """Create a payment for an order using Mercado Pago."""
        import mercadopago

        if payment_method == 'cash':
            order.payment_method = 'cash'
            order.payment_status = StoreOrder.PaymentStatus.PENDING
            order.save(update_fields=['payment_method', 'payment_status', 'updated_at'])

            return {
                'success': True,
                'payment_id': None,
                'status': 'pending',
                'payment_method': 'cash',
                'message': 'Pagamento em dinheiro na entrega/retirada'
            }

        credentials = CheckoutService.get_payment_credentials(order.store)
        if not credentials:
            raise ValueError("Credenciais de pagamento nao configuradas")

        sdk = mercadopago.SDK(credentials['access_token'])
        payer_email = get_valid_email_for_payment(order)
        logger.info(f"Using email for payment: {payer_email} (original: {order.customer_email})")

        payment_payload = payment_data or {}

        if payment_method == 'pix':
            pix_payment_data = {
                "transaction_amount": float(order.total),
                "description": f"Pedido #{order.order_number} - {order.store.name}",
                "payment_method_id": "pix",
                "payer": {
                    "email": payer_email,
                    "first_name": order.customer_name.split()[0] if order.customer_name else "Cliente",
                    "last_name": " ".join(order.customer_name.split()[1:]) if order.customer_name else "",
                },
                "external_reference": str(order.id),
                "notification_url": f"{settings.BASE_URL}/webhooks/payments/mercadopago/",
            }

            result = sdk.payment().create(pix_payment_data)

            if result["status"] == 201:
                payment = result["response"]
                order.payment_id = str(payment["id"])
                order.payment_method = 'pix'
                order.payment_status = StoreOrder.PaymentStatus.PENDING

                pix_data = payment.get("point_of_interaction", {}).get("transaction_data", {})
                order.pix_code = pix_data.get("qr_code", "")
                order.pix_qr_code = pix_data.get("qr_code_base64", "")
                ticket_url = pix_data.get("ticket_url", "")
                order.pix_ticket_url = ticket_url
                order.save(update_fields=[
                    'payment_id',
                    'payment_method',
                    'payment_status',
                    'pix_code',
                    'pix_qr_code',
                    'pix_ticket_url',
                    'updated_at',
                ])

                return {
                    'success': True,
                    'payment_id': payment["id"],
                    'status': payment["status"],
                    'payment_method': 'pix',
                    'pix_code': order.pix_code,
                    'pix_qr_code': order.pix_qr_code,
                    'ticket_url': ticket_url,
                    'expiration': pix_data.get("expiration_date"),
                    'requires_redirect': False,
                }

            logger.error(f"Payment creation failed: {result}")
            return {
                'success': False,
                'error': result.get("response", {}).get("message", "Erro ao criar pagamento"),
            }

        if payment_method in {'credit_card', 'debit_card', 'card'}:
            card_token = payment_payload.get('token')
            payment_method_id = payment_payload.get('payment_method_id')
            payer_data = payment_payload.get('payer', {}) if isinstance(payment_payload.get('payer'), dict) else {}
            identification_type = payer_data.get('identification_type') or payer_data.get('identificationType')
            identification_number = payer_data.get('identification_number') or payer_data.get('identificationNumber')
            storefront_base_url = CheckoutService.get_storefront_base_url(order.store, payment_payload)
            allow_redirect = bool(
                payment_payload.get('allow_redirect')
                or payment_payload.get('use_hosted_checkout')
                or payment_payload.get('hosted_checkout')
            )

            if card_token and payment_method_id:
                installments = payment_payload.get('installments') or 1
                try:
                    installments = int(installments)
                except (TypeError, ValueError):
                    installments = 1

                direct_payment_data = {
                    "transaction_amount": float(order.total),
                    "token": card_token,
                    "description": f"Pedido #{order.order_number} - {order.store.name}",
                    "installments": max(1, installments),
                    "payment_method_id": payment_method_id,
                    "payer": {
                        "email": payer_data.get('email') or payer_email,
                    },
                    "external_reference": str(order.id),
                    "notification_url": f"{settings.BASE_URL}/webhooks/payments/mercadopago/",
                }

                issuer_id = payment_payload.get('issuer_id')
                if issuer_id:
                    direct_payment_data['issuer_id'] = issuer_id

                if identification_type and identification_number:
                    direct_payment_data['payer']['identification'] = {
                        'type': identification_type,
                        'number': identification_number,
                    }

                result = sdk.payment().create(direct_payment_data)

                if result["status"] in (200, 201):
                    payment = result["response"]
                    payment_status = payment.get('status', 'pending')

                    order.payment_id = str(payment['id'])
                    order.payment_method = payment_method

                    if payment_status == 'approved':
                        order.status = StoreOrder.OrderStatus.CONFIRMED
                        order.payment_status = StoreOrder.PaymentStatus.PAID
                        order.paid_at = timezone.now()
                        if not order.confirmed_at:
                            order.confirmed_at = timezone.now()
                    elif payment_status in {'in_process', 'pending'}:
                        order.payment_status = (
                            StoreOrder.PaymentStatus.PROCESSING
                            if payment_status == 'in_process'
                            else StoreOrder.PaymentStatus.PENDING
                        )
                    else:
                        order.status = StoreOrder.OrderStatus.FAILED
                        order.payment_status = StoreOrder.PaymentStatus.FAILED

                    order.save()

                    return {
                        'success': True,
                        'payment_id': payment['id'],
                        'status': payment_status,
                        'status_detail': payment.get('status_detail', ''),
                        'payment_method': payment_method,
                        'requires_redirect': False,
                    }

                logger.error(f"Direct card payment failed: {result}")
                return {
                    'success': False,
                    'error': result.get('response', {}).get('message', 'Erro ao processar pagamento com cartao'),
                }

            if not allow_redirect:
                missing_fields = []
                if not card_token:
                    missing_fields.append('token')
                if not payment_method_id:
                    missing_fields.append('payment_method_id')

                missing_fields_str = ', '.join(missing_fields) if missing_fields else 'dados do cartao'
                logger.warning(
                    "Direct card payment requested without required Mercado Pago data for order %s. Missing: %s",
                    order.order_number,
                    missing_fields_str,
                )
                return {
                    'success': False,
                    'error': f'Dados do cartao incompletos para pagamento direto ({missing_fields_str}).',
                }

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
                    "email": payer_email,
                    "name": order.customer_name,
                    "phone": {"number": order.customer_phone},
                },
                "external_reference": str(order.id),
                "back_urls": {
                    "success": f"{storefront_base_url}/sucesso?order={order.id}",
                    "failure": f"{storefront_base_url}/erro?order={order.id}",
                    "pending": f"{storefront_base_url}/pendente?order={order.id}",
                },
                "auto_return": "approved",
                "notification_url": f"{settings.BASE_URL}/webhooks/payments/mercadopago/",
            }

            result = sdk.preference().create(preference_data)

            if result["status"] == 201:
                preference = result["response"]
                order.payment_preference_id = preference['id']
                order.payment_method = payment_method
                order.payment_status = StoreOrder.PaymentStatus.PENDING
                order.save(update_fields=[
                    'payment_preference_id',
                    'payment_method',
                    'payment_status',
                    'updated_at',
                ])

                return {
                    'success': True,
                    'preference_id': preference['id'],
                    'payment_method': payment_method,
                    'status': 'pending',
                    'requires_redirect': True,
                    'init_point': preference['init_point'],
                    'sandbox_init_point': preference.get('sandbox_init_point'),
                }

            logger.error(f"Preference creation failed: {result}")
            return {
                'success': False,
                'error': result.get('response', {}).get('message', 'Erro ao criar preferencia'),
            }

        raise ValueError(f"Metodo de pagamento nao suportado: {payment_method}")

    @staticmethod
    @transaction.atomic
    def process_payment_webhook(payment_id: str, status: str) -> StoreOrder:
        """Process payment webhook and update order status."""
        order = StoreOrder.objects.select_for_update().filter(
            payment_id=payment_id
        ).first()
        
        if not order:
            logger.warning(f"Order not found for payment {payment_id}")
            return None
        
        old_status = order.status
        
        update_fields = ['updated_at']

        if status == 'approved':
            order.payment_status = StoreOrder.PaymentStatus.PAID
            order.paid_at = timezone.now()
            if order.status in {
                StoreOrder.OrderStatus.PENDING,
                StoreOrder.OrderStatus.PROCESSING,
                StoreOrder.OrderStatus.PAID,
            }:
                order.status = StoreOrder.OrderStatus.CONFIRMED
                if not order.confirmed_at:
                    order.confirmed_at = timezone.now()
                update_fields.extend(['status', 'confirmed_at'])
            update_fields.extend(['payment_status', 'paid_at'])
            trigger_order_email_automation(order, 'payment_confirmed')

        elif status == 'pending':
            order.payment_status = StoreOrder.PaymentStatus.PENDING
            update_fields.append('payment_status')

        elif status == 'in_process':
            order.payment_status = StoreOrder.PaymentStatus.PROCESSING
            update_fields.append('payment_status')

        elif status in {'rejected', 'cancelled'}:
            order.status = StoreOrder.OrderStatus.CANCELLED
            order.payment_status = StoreOrder.PaymentStatus.FAILED
            order.cancelled_at = timezone.now()
            update_fields.extend(['status', 'payment_status', 'cancelled_at'])
            CheckoutService._restore_stock(order)
            trigger_order_email_automation(order, 'order_cancelled')

        elif status == 'refunded':
            order.status = StoreOrder.OrderStatus.REFUNDED
            order.payment_status = StoreOrder.PaymentStatus.REFUNDED
            order.cancelled_at = timezone.now()
            update_fields.extend(['status', 'payment_status', 'cancelled_at'])
            CheckoutService._restore_stock(order)

        else:
            return order

        order.save(update_fields=list(dict.fromkeys(update_fields)))

        if status == 'approved':
            try:
                from apps.stores.services.meta_pixel_service import send_purchase_event
                send_purchase_event(order)
            except Exception as exc:
                logger.warning(f"Meta Pixel CAPI failed for {order.order_number}: {exc}")

        logger.info(f"Order {order.order_number} status updated: {old_status} -> {order.status} | payment={order.payment_status}")
        
        return order
    
    @staticmethod
    def _restore_stock(order: StoreOrder):
        """Restore stock for cancelled/refunded orders."""
        for item in order.items.all():
            if item.product and item.product.track_stock:
                if item.variant:
                    from apps.stores.models import StoreProductVariant
                    StoreProductVariant.objects.filter(id=item.variant.id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )
                else:
                    StoreProduct.objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') + item.quantity,
                        sold_count=F('sold_count') - item.quantity
                    )


# Singleton instance
checkout_service = CheckoutService()
