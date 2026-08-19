"""
Checkout Service - Unified checkout for all stores.
Handles order creation, payment processing, and stock management.
"""
import logging
import re
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from apps.core.services.customer_identity import CustomerIdentityService

_PLACEHOLDER_EMAIL_DOMAINS = ('@local.invalid', '@whatsapp.bot', '@cliente.pastita.com.br')


def is_placeholder_email(email: str) -> bool:
    if not email:
        return True
    return any(email.endswith(d) for d in _PLACEHOLDER_EMAIL_DOMAINS)
from apps.stores.models import (
    Store, StoreCart, StoreOrder, StoreOrderItem, StoreOrderComboItem,
    StoreProduct, StoreProductVariant, StoreIntegration,
    StoreCoupon
)
from apps.stores.services.delivery_quote_service import DeliveryQuoteService
from .cart_service import cart_service

logger = logging.getLogger(__name__)


def _invalidate_agent_menu_safe(store_id) -> None:
    """Invalida o cardápio cacheado do agente sem nunca quebrar o checkout.

    Import tardio p/ evitar ciclo (langchain_service importa models de stores).
    """
    try:
        from apps.agents.services.langchain_service import invalidate_menu_context
        invalidate_menu_context(store_id)
    except Exception as e:
        logger.warning("Falha ao invalidar menu_ctx do agente no checkout: %s", e)


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
    if email and not is_placeholder_email(email):
        domain = email.split('@')[-1].lower()
        if not domain.endswith('.local') and not domain.endswith('.test') and not domain.endswith('.invalid'):
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

        metadata = order.metadata or {}
        if metadata.get('source') == 'whatsapp' or is_placeholder_email(order.customer_email):
            logger.debug(f"Placeholder/WhatsApp email for order {order.order_number}, skipping email automation")
            return

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
    def build_combo_selection_snapshot(combo_item) -> dict:
        """Resolve combo variant UUID selections into an order-time display snapshot."""
        return CheckoutService.build_combo_selection_snapshots([combo_item])[combo_item.id]

    @staticmethod
    def _normalize_group_selections(combo_item) -> dict:
        group_selections = combo_item.group_selections or combo_item.customizations.get('selections', {})
        return {
            str(group_id): [
                str(variant_id)
                for variant_id in (variant_ids if isinstance(variant_ids, list) else [variant_ids])
                if variant_id
            ]
            for group_id, variant_ids in (group_selections or {}).items()
        }

    @staticmethod
    def build_combo_selection_snapshots(combo_items) -> dict:
        """Versão em lote do snapshot: resolve grupos/variantes/produtos de
        TODOS os combo_items em nº constante de queries (serialização do
        carrinho é O(1) em relação ao nº de combos)."""
        from apps.stores.models.combo_group import ComboProductGroup

        combo_items = list(combo_items)
        normalized_by_item = {
            combo_item.id: CheckoutService._normalize_group_selections(combo_item)
            for combo_item in combo_items
        }
        all_selected_ids = sorted({
            variant_id
            for normalized in normalized_by_item.values()
            for variant_ids in normalized.values()
            for variant_id in variant_ids
        })
        combo_ids = {ci.combo_id for ci in combo_items if ci.combo_id}

        groups_by_combo = {}
        if combo_ids:
            for group in ComboProductGroup.objects.filter(combo_id__in=combo_ids).select_related('product'):
                groups_by_combo.setdefault(group.combo_id, {})[str(group.id)] = group

        variants = StoreProductVariant.objects.filter(id__in=all_selected_ids).select_related('product')
        variants_by_id = {str(variant.id): variant for variant in variants}
        # IDs que NÃO são variantes -> resolver como PRODUTO (opções de produto
        # no grupo). UUID de variante e de produto não colidem, então dá pra
        # misturar no mesmo group_selections sem quebrar combos de variante.
        product_only_ids = [i for i in all_selected_ids if i not in variants_by_id]
        products_by_id = {
            str(p.id): p for p in StoreProduct.objects.filter(id__in=product_only_ids)
        }

        return {
            combo_item.id: CheckoutService._assemble_selection_snapshot(
                normalized_by_item[combo_item.id],
                groups_by_combo.get(combo_item.combo_id, {}),
                variants_by_id,
                products_by_id,
            )
            for combo_item in combo_items
        }

    @staticmethod
    def _assemble_selection_snapshot(normalized_groups, groups_by_id, variants_by_id, products_by_id) -> dict:
        selected_variant_ids = [
            variant_id
            for variant_ids in normalized_groups.values()
            for variant_id in variant_ids
        ]

        def _group_label(grp):
            if not grp:
                return ''
            return (grp.title or (grp.product.name if grp.product_id else '')) or ''

        selected_variants_data = []
        display_groups = []
        for group_id, sel_ids in normalized_groups.items():
            group = groups_by_id.get(group_id)
            counts = {}
            for sid in sel_ids:
                counts[sid] = counts.get(sid, 0) + 1

            group_items = []
            for sid, quantity in counts.items():
                variant = variants_by_id.get(sid)
                if variant is not None:
                    item_data = {
                        'group_id': group_id,
                        'group_name': _group_label(group),
                        'variant_id': sid,
                        'variant_name': variant.name,
                        'product_id': str(variant.product_id),
                        'product_name': variant.product.name if variant.product else '',
                        'quantity': quantity,
                        'sku': variant.sku,
                    }
                else:
                    prod = products_by_id.get(sid)
                    item_data = {
                        'group_id': group_id,
                        'group_name': _group_label(group),
                        'variant_id': '',
                        'variant_name': '',
                        'product_id': sid if prod else '',
                        'product_name': prod.name if prod else '',
                        'quantity': quantity,
                        'sku': getattr(prod, 'sku', '') if prod else '',
                    }
                selected_variants_data.append(item_data)
                group_items.append(item_data)

            display_groups.append({
                'group_id': group_id,
                'group_name': _group_label(group),
                'items': group_items,
            })

        # selected_variant_ids fica só com variantes REAIS (compat downstream);
        # produtos escolhidos vão em selected_product_ids.
        real_variant_ids = [i for i in selected_variant_ids if i in variants_by_id]
        selected_product_ids = [i for i in selected_variant_ids if i in products_by_id]

        return {
            'group_selections': normalized_groups,
            'selected_variant_ids': real_variant_ids,
            'selected_product_ids': selected_product_ids,
            'selected_variants_data': selected_variants_data,
            'display_groups': display_groups,
        }

    @staticmethod
    def _normalize_base_url(raw_url: str) -> str:
        """Return scheme + host only for a storefront or app deep link base URL."""
        if not raw_url:
            return ''

        candidate = str(raw_url).strip()
        if not candidate:
            return ''

        # A env pode trazer uma LISTA no estilo de origens permitidas —
        # FRONTEND_URL em produção vale
        # 'https://cardapidex.com.br,https://painel.pastita.com.br'. Sem
        # separar, o host virava 'cardapidex.com.br,https:' e o link ia
        # quebrado para o cliente: é a mesma função que monta o redirect
        # pós-pagamento e o link de avaliação do pedido no WhatsApp.
        if ',' in candidate:
            for parte in candidate.split(','):
                normalizada = CheckoutService._normalize_base_url(parte)
                if normalizada:
                    return normalizada
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
    def record_coupon_redemption(order, coupon) -> None:
        """Trilha cupom×pedido (BI Fase 2). Idempotente: OneToOne com o pedido."""
        from apps.stores.models import StoreCouponRedemption
        if not order or not coupon:
            return
        try:
            StoreCouponRedemption.objects.get_or_create(
                order=order,
                defaults={
                    'store': order.store,
                    'coupon': coupon,
                    'code': (order.coupon_code or coupon.code or '').upper(),
                    'amount': order.discount or 0,
                    'customer_phone': order.customer_phone or '',
                },
            )
        except Exception:
            logger.warning('Falha ao registrar resgate de cupom do pedido %s', order.id, exc_info=True)

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
        return DeliveryQuoteService.calculate_for_distance(store, distance_km=distance_km, zip_code=zip_code)
    
    @staticmethod
    def _calculate_dynamic_fee(store: Store, distance_km: Decimal = None) -> dict:
        """Calculate delivery fee dynamically based on distance.

        Delega a DeliveryQuoteService.calculate_dynamic_fee — a fonte única da
        matemática de taxa dinâmica.

        Pricing:
          - base plana até 4 km (delivery_flat_km)
          - base + (dist - 4) × R$ 1,00 acima de 4 km
          - Acima de 16 km: fee=None (a combinar)
          base = metadata['delivery_base_fee'] OU store.default_delivery_fee OU 9.00.

        Overridable via store.metadata keys:
          delivery_base_fee      (default: store.default_delivery_fee, senão 9.00)
          delivery_fee_per_km    (default 1.00)
          delivery_flat_km       (default 4.0 — distância onde a taxa é plana)
          delivery_free_km       (legacy alias for delivery_flat_km)
          delivery_max_km        (default 16.0 — acima disso retorna fee=None)
          delivery_max_fee       (optional legacy cap; when present, caps fee instead of out-of-range)
        """
        return DeliveryQuoteService.calculate_dynamic_fee(store, distance_km)

    @staticmethod
    def normalize_delivery_quote(info: dict, route: dict = None) -> dict:
        """Return a stable delivery quote while preserving legacy response keys."""
        return DeliveryQuoteService.normalize(info, route)

    @staticmethod
    def calculate_delivery_fee_for_payload(store: Store, delivery_payload: dict) -> dict:
        """Resolve a delivery fee from distance, coordinates, or address text.

        Delegated to UnifiedDeliveryService — single source of truth for all delivery fees.
        """
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        import logging
        logger = logging.getLogger(__name__)

        payload = delivery_payload or {}

        # Convert address dict to string if needed
        address_obj = payload.get('address')
        address_text = None

        if isinstance(address_obj, str):
            address_text = address_obj
        elif isinstance(address_obj, dict):
            parts = [
                address_obj.get('street', ''),
                address_obj.get('number', ''),
                address_obj.get('neighborhood', ''),
                address_obj.get('city', ''),
                address_obj.get('state', ''),
            ]
            address_text = ', '.join(filter(None, parts)) or None

        logger.info(f"calculate_delivery_fee_for_payload: lat={payload.get('lat')}, lng={payload.get('lng')}, address_text={address_text}")
        result = UnifiedDeliveryService.calculate_delivery_fee(
            store=store,
            delivery_method=payload.get('method', 'delivery'),
            address_text=address_text,
            lat=payload.get('lat'),
            lng=payload.get('lng'),
            rain_surcharge=payload.get('rain_surcharge', False),
        )

        # Normalize to DeliveryQuoteService contract for backwards compatibility
        return {
            'fee': result.get('fee'),
            'distance_km': result.get('distance_km'),
            'duration_minutes': result.get('duration_minutes'),
            'is_valid': result.get('success', False),
            'available': result.get('success', False),
            'message': result.get('reason', 'OK' if result.get('success') else 'Erro'),
            'zone_name': result.get('zone_name', 'Dinâmica'),
        }

    @staticmethod
    def normalize_custom_salad_payload(customizations: dict, combo_name: str, unit_price=None) -> dict:
        """Validate and normalize mobile salad-builder customizations."""
        data = dict(customizations or {})
        ingredients_raw = data.get('ingredients') or []
        if isinstance(ingredients_raw, str):
            ingredients = [part.strip() for part in ingredients_raw.split('·') if part.strip()]
        elif isinstance(ingredients_raw, list):
            ingredients = []
            for part in ingredients_raw:
                if isinstance(part, dict):
                    label = part.get('name') or part.get('label') or part.get('ingredient_name')
                    if label:
                        ingredients.append(part)
                    continue
                value = str(part).strip()
                if value:
                    ingredients.append(value)
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
        """Status de fidelidade lendo do saldo persistido (StoreLoyaltyAccount).

        Na primeira leitura de um cliente sem conta, faz backfill do histórico
        de pedidos (lógica legada) para a trilha persistida — depois disso toda
        leitura é O(1) e os créditos novos chegam via OrderService/checkout.
        """
        from apps.stores.services.loyalty_service import LoyaltyService

        if user and getattr(user, 'is_authenticated', False):
            CheckoutService._ensure_loyalty_backfilled(store, user)
        status = LoyaltyService.get_status(store, user)
        available = status['available_rewards']
        status['remaining'] = 0 if available else status['remaining']
        _, item_label_plural = LoyaltyService.item_labels(store)
        status['label'] = f"A cada {status['threshold']} {item_label_plural}, 1 grátis"
        return status

    @staticmethod
    def _ensure_loyalty_backfilled(store: Store, user) -> None:
        from apps.stores.models import StoreLoyaltyAccount
        from apps.stores.services.loyalty_service import LoyaltyService

        if StoreLoyaltyAccount.objects.filter(store=store, user=user).exists():
            return
        legacy = CheckoutService._compute_loyalty_from_history(store, user)
        # Cria a conta mesmo zerada para não re-escanear a cada request
        LoyaltyService._get_account(store, user)
        if legacy['qualified_salads']:
            for order_id, qty in legacy.get('per_order_qualified', {}).items():
                order = StoreOrder.objects.filter(id=order_id).first()
                if order and qty:
                    LoyaltyService.credit_qualified(store, user, order, qty)
        if legacy['rewards_redeemed']:
            LoyaltyService.backfill_redeemed(store, user, legacy['rewards_redeemed'])

    @staticmethod
    def _compute_loyalty_from_history(store: Store, user=None) -> dict:
        from apps.stores.services.loyalty_service import LoyaltyService

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
        per_order_qualified = {}
        for order in orders:
            loyalty_meta = (order.metadata or {}).get('loyalty_reward') or {}
            if loyalty_meta.get('applied'):
                redeemed += int(loyalty_meta.get('count') or 1)
            order_qty = LoyaltyService.order_qualified_units(store, order)
            if order_qty:
                per_order_qualified[str(order.id)] = order_qty
                qualified += order_qty

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
            'per_order_qualified': per_order_qualified,
        }

    @staticmethod
    def _cart_salad_discount(cart: StoreCart) -> Decimal:
        from apps.stores.services.loyalty_service import LoyaltyService

        prices = []
        for item in cart.items.select_related('product__category', 'product__product_type', 'variant').all():
            if LoyaltyService.cart_item_qualifies(cart.store, item):
                prices.extend([Decimal(str(item.unit_price))] * int(item.quantity or 0))
        for item in cart.combo_items.all():
            if LoyaltyService.cart_item_qualifies(cart.store, item):
                prices.extend([Decimal(str(item.effective_price))] * int(item.quantity or 0))
        return min(prices) if prices else Decimal('0')
    
    @staticmethod
    def _coupon_items(cart: StoreCart) -> list:
        """Itens do carrinho no formato que o cupom usa pra escopo por
        produto/categoria (combos ficam de fora — cupom escopado é de produto)."""
        items = []
        for item in cart.items.select_related('product').all():
            product = item.product
            items.append({
                'product_id': str(item.product_id) if item.product_id else '',
                'category_id': str(product.category_id) if product and product.category_id else '',
                'total': Decimal(str(item.unit_price)) * int(item.quantity or 0),
            })
        return items

    @staticmethod
    def validate_coupon(store: Store, code: str, subtotal: Decimal, user=None,
                        customer_phone: str = None, items: list = None) -> dict:
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
            is_valid, error_message = coupon.is_valid(
                subtotal=subtotal, user=user, customer_phone=customer_phone,
            )
            if not is_valid:
                return {'valid': False, 'error': error_message}

            discount = coupon.calculate_discount(subtotal, items=items)
            
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
        """Calculate order totals.

        cart.subtotal already aggregates both regular items and combo items,
        so there is no need to iterate over combo_items separately.
        """
        subtotal = Decimal(str(cart.subtotal))

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
    def create_order(
        cart: StoreCart,
        customer_data: dict,
        delivery_data: dict = None,
        coupon_code: str = None,
        notes: str = '',
        use_loyalty_reward: bool = False,
        trusted_delivery_fee: "Decimal | None" = None,
        scheduled_date=None,
        scheduled_time='',
    ) -> StoreOrder:
        """Create an order from a cart.

        A taxa de entrega (que pode disparar geocode/route HTTP no
        UnifiedDeliveryService) é calculada AQUI, FORA de qualquer transação,
        para não segurar a conexão do banco durante I/O de rede. A escrita
        (estoque + pedido) roda em `_create_order_atomic`, que recebe a taxa
        já pronta via `precomputed_delivery_info`.
        """
        store = cart.store
        delivery_payload = dict(delivery_data or {})

        precomputed_delivery_info = None
        needs_fee_calc = (
            trusted_delivery_fee is None
            and delivery_payload.get('method') == 'delivery'
            and delivery_payload.get('fee') is None
        )
        if needs_fee_calc:
            # Espelha a sanitização/defaults do corpo atômico só para computar a
            # taxa; o endereço definitivo é re-sanitizado lá dentro.
            addr = _sanitize_delivery_address_coordinates(dict(delivery_payload.get('address') or {}))
            if store.city and not addr.get('city'):
                addr['city'] = store.city
            if store.state and not addr.get('state'):
                addr['state'] = store.state
            info = CheckoutService.calculate_delivery_fee_for_payload(
                store, {**delivery_payload, 'address': addr},
            )
            precomputed_delivery_info = CheckoutService.normalize_delivery_quote(info)
            # Não levanta aqui: o corpo atômico valida fee None → ValueError,
            # mantendo mensagem/rollback idênticos ao comportamento anterior.

        return CheckoutService._create_order_atomic(
            cart=cart,
            customer_data=customer_data,
            delivery_data=delivery_data,
            coupon_code=coupon_code,
            notes=notes,
            use_loyalty_reward=use_loyalty_reward,
            trusted_delivery_fee=trusted_delivery_fee,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            precomputed_delivery_info=precomputed_delivery_info,
        )

    @staticmethod
    @transaction.atomic
    def _create_order_atomic(
        cart: StoreCart,
        customer_data: dict,
        delivery_data: dict = None,
        coupon_code: str = None,
        notes: str = '',
        use_loyalty_reward: bool = False,
        trusted_delivery_fee: "Decimal | None" = None,
        scheduled_date=None,
        scheduled_time='',
        precomputed_delivery_info: dict = None,
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
        
        # Validate trusted_delivery_fee early so callers get a clear error.
        if trusted_delivery_fee is not None and trusted_delivery_fee < 0:
            raise ValueError("trusted_delivery_fee não pode ser negativo")

        # Calculate delivery fee
        delivery_info = CheckoutService.normalize_delivery_quote({
            'fee': 0.0,
            'delivery_fee': 0.0,
            'zone_name': 'Retirada',
            'is_valid': True,
            'available': True,
        })
        if trusted_delivery_fee is not None:
            # Caller already computed the fee; use it verbatim.
            delivery_info = CheckoutService.normalize_delivery_quote({
                **(delivery_payload or {}),
                'fee': float(trusted_delivery_fee),
                'is_valid': True,
                'available': True,
            })
        elif delivery_payload and delivery_payload.get('method') == 'delivery':
            if delivery_payload.get('fee') is not None:
                # Pre-computed fee (WhatsApp override or GeoService result); skip recalculation.
                delivery_info = CheckoutService.normalize_delivery_quote({
                    **delivery_payload,
                    'is_valid': True,
                    'available': True,
                })
            elif precomputed_delivery_info is not None:
                # Taxa já calculada FORA da transação pelo create_order público
                # (evita geocode/route HTTP segurando a conexão do banco).
                delivery_info = precomputed_delivery_info
            else:
                # Fallback defensivo: chamada direta a _create_order_atomic sem
                # taxa pré-computada — calcula inline (raro; caminho público
                # sempre passa precomputed_delivery_info).
                delivery_info = CheckoutService.calculate_delivery_fee_for_payload(
                    store,
                    delivery_payload,
                )
                delivery_info = CheckoutService.normalize_delivery_quote(delivery_info)
        
        if delivery_info.get('fee') is None:
            raise ValueError(delivery_info.get('message') or 'Endereço fora da área de entrega')

        delivery_fee = Decimal(str(delivery_info['fee']))
        
        # Calculate subtotal — select_related avoids N+1 on unit_price access
        subtotal = Decimal('0')
        for item in cart.items.select_related('product', 'variant').all():
            subtotal += item.subtotal
        for combo_item in cart.combo_items.select_related('combo').all():
            subtotal += combo_item.subtotal

        customer_record = CustomerIdentityService.sync_checkout_customer(
            store=store,
            customer_name=customer_data.get('name', ''),
            email=customer_data.get('email', ''),
            phone=customer_data.get('phone', ''),
            cpf=customer_data.get('cpf', ''),
            accepts_marketing=customer_data.get('accepts_marketing'),
            delivery_method=delivery_payload.get('method', '') if delivery_payload else '',
            delivery_address=delivery_payload.get('address', {}) if delivery_payload else {},
            user=cart.user,
        )
        customer_user = customer_record.get('user')
        store_customer = customer_record.get('store_customer')
        
        # Validate and apply coupon using unified StoreCoupon model
        discount = Decimal('0')
        coupon = None
        coupon_rejected = None   # {'code', 'reason'} quando o cupom não pegou
        if coupon_code:
            coupon_result = CheckoutService.validate_coupon(
                store, coupon_code, subtotal,
                user=cart.user,
                customer_phone=(customer_data.get('phone') or '').strip() or None,
                items=CheckoutService._coupon_items(cart),
            )
            if coupon_result['valid']:
                # RESERVA a vaga antes de conceder o desconto. `validate_coupon`
                # leu `used_count` lá atrás; entre aquela leitura e aqui, outros
                # checkouts podem ter esgotado o cupom. `increment_usage()` é
                # atômico (`used_count__lt=usage_limit` no WHERE) e devolve False
                # quando não havia vaga — antes esse retorno era descartado e o
                # desconto saía assim mesmo, para todos os concorrentes.
                # Estamos dentro de _create_order_atomic: se o pedido reverter,
                # a reserva reverte junto.
                candidate = StoreCoupon.objects.get(id=coupon_result['coupon_id'])
                if candidate.increment_usage():
                    coupon = candidate
                    discount = Decimal(str(coupon_result['discount']))
                else:
                    logger.info(
                        'Cupom %s esgotou na corrida (limite %s); pedido segue sem desconto',
                        coupon_code, candidate.usage_limit,
                    )
                    coupon_rejected = {
                        'code': coupon_code,
                        'reason': 'Limite de uso atingido',
                    }
            else:
                # O cupom foi recusado AQUI, depois de a tela já ter mostrado o
                # desconto (a validação do storefront acontece antes e pode ter
                # sido aprovada). Registrar o motivo: sem isso, o pedido saía com
                # o código gravado e desconto zero, e nem o cliente nem o
                # atendente conseguiam explicar o "-" na coluna de desconto.
                coupon_rejected = {
                    'code': coupon_code,
                    'reason': coupon_result.get('error') or 'Cupom inválido',
                }
                logger.info(
                    'Cupom %s recusado no checkout (%s); pedido segue sem desconto',
                    coupon_code, coupon_rejected['reason'],
                )

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
        
        # Calculate total (no tax - just subtotal + delivery - discount).
        # HOTFIX: cupom percentual gera desconto com 3+ casas (ex: 44.99*10% =
        # 4.499 -> total 40.491). float(40.491) faz o Mercado Pago rejeitar com
        # "Invalid transaction_amount" (code 4037) = checkout 400. Quantiza
        # desconto e total para centavos (2 casas) e nunca deixa total negativo.
        _CENTS = Decimal('0.01')
        discount = discount.quantize(_CENTS, rounding=ROUND_HALF_UP)
        total = (subtotal + delivery_fee - discount).quantize(_CENTS, rounding=ROUND_HALF_UP)
        if total < Decimal('0'):
            total = Decimal('0.00')

        extra_metadata = dict(delivery_payload.get('metadata') or {})

        # Create order
        order = StoreOrder.objects.create(
            store=store,
            customer=customer_user or cart.user,
            customer_name=customer_data.get('name') or '',
            customer_email=customer_data.get('email') or '',
            customer_phone=customer_data.get('phone') or '',
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            subtotal=subtotal,
            discount=discount,
            # Só grava o código que REALMENTE valeu. Antes gravava a string crua:
            # cupom recusado virava pedido com código preenchido e desconto 0,00,
            # o painel mostrava "-" e o cliente jurava ter aplicado. O código
            # recusado fica em metadata['coupon_rejected'] para auditoria.
            coupon_code=(coupon.code if coupon else ''),
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
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time or '',
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
                **({'coupon_rejected': coupon_rejected} if coupon_rejected else {}),
                **extra_metadata,
            }
        )
        if customer_user and customer_user != cart.user:
            # O cliente fechou como convidado, mas o e-mail/telefone casou com
            # uma conta existente. Se essa conta já tinha um carrinho ativo
            # abandonado, reivindicar este aqui violava
            # unique_active_cart_per_user_store e o checkout inteiro morria em
            # 400 ("Erro ao processar checkout"). Desativa o carrinho órfão
            # antes de reivindicar — este carrinho é o que virou pedido e será
            # desativado logo abaixo de qualquer forma.
            StoreCart.objects.filter(
                store=store,
                user=customer_user,
                is_active=True,
            ).exclude(pk=cart.pk).update(is_active=False)
            cart.user = customer_user
            cart.save(update_fields=['user', 'updated_at'])

        if coupon is not None:
            CheckoutService.record_coupon_redemption(order, coupon)
            # Indicação: amigo usou cupom INDICA → premia o indicador (best-effort)
            from apps.stores.services.referral_service import ReferralService
            ReferralService.reward_referrer_if_applicable(order, coupon)

        # Fidelidade persistida: registra o resgate na trilha auditável
        if loyalty_reward.get('applied'):
            loyalty_user = customer_user or cart.user
            if loyalty_user:
                from apps.stores.services.loyalty_service import LoyaltyService
                try:
                    LoyaltyService.redeem(store, loyalty_user, order, rewards=int(loyalty_reward.get('count') or 1))
                except ValueError:
                    # can_redeem já foi validado acima; corrida rara → não bloquear o pedido
                    logger.warning('Loyalty redeem sem saldo no pedido %s', order.id)
        
        # Create order items and decrement stock
        stock_changed = False
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
                    # Estoque a nível de produto mudou → o cardápio cacheado do
                    # agente (nota [ESGOTADO]/[últimas N]) precisa ser invalidado.
                    # O .update()/F() acima NÃO dispara post_save, então a
                    # invalidação por signal não cobre este caminho.
                    stock_changed = True

        # Handle combo items (real and virtual)
        for combo_item in cart.combo_items.select_related('combo').all():
            is_virtual = combo_item.combo is None
            display_name = combo_item.effective_name
            effective_price = combo_item.effective_price

            if not is_virtual:
                display_name = f"Combo: {display_name}"

            order_item = StoreOrderItem.objects.create(
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

            if not is_virtual:
                selection_snapshot = CheckoutService.build_combo_selection_snapshot(combo_item)
                StoreOrderComboItem.objects.create(
                    order=order,
                    order_item=order_item,
                    combo=combo_item.combo,
                    quantity=combo_item.quantity,
                    group_selections=selection_snapshot['group_selections'],
                    selected_variant_ids=selection_snapshot['selected_variant_ids'],
                    selected_variants_data=selection_snapshot['selected_variants_data'],
                    display_data={
                        'combo_name': combo_item.effective_name,
                        'unit_price': str(combo_item.effective_price),
                        'customizations': combo_item.customizations,
                        'groups': selection_snapshot['display_groups'],
                    },
                )

            # Decrement combo stock if tracked (real combos only)
            if not is_virtual and combo_item.combo.track_stock:
                from apps.stores.models import StoreCombo
                StoreCombo.objects.filter(id=combo_item.combo.id).update(
                    stock_quantity=F('stock_quantity') - combo_item.quantity
                )
        
        # Invalida o cardápio cacheado do agente quando o estoque de produto
        # mudou (só após o commit, p/ não invalidar se a transação reverter).
        if stock_changed:
            store_id = order.store_id
            transaction.on_commit(
                lambda: _invalidate_agent_menu_safe(store_id)
            )

        # (o incremento do cupom virou RESERVA e acontece lá em cima, junto da
        # aplicação do desconto — incrementar aqui contaria duas vezes)

        if store_customer:
            store_customer.last_order_at = timezone.now()
            store_customer.save(update_fields=['last_order_at', 'updated_at'])
        
        # Clear the cart
        cart.clear()
        cart.is_active = False
        cart.save()

        from apps.stores.services.print_service import enqueue_order_print_job
        transaction.on_commit(
            lambda order_id=order.id: enqueue_order_print_job(
                StoreOrder.objects.get(id=order_id)
            )
        )
        
        logger.info(f"Order {order.order_number} created for store {store.slug}")
        
        # Trigger order received email automation (NOT confirmed - payment pending)
        # The 'order_confirmed' / 'payment_confirmed' email will ONLY be sent
        # after payment is confirmed via webhook
        trigger_order_email_automation(order, 'order_received')
        
        return order
    
    @staticmethod
    def get_payment_credentials(store: Store) -> dict:
        """Get payment credentials for a store.

        Priority: StorePaymentGateway → StoreIntegration (legacy) → global settings.
        """
        from apps.stores.models import StorePaymentGateway
        gateway = StorePaymentGateway.objects.filter(
            store=store,
            gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
            is_enabled=True,
        ).first()

        if gateway and gateway.access_token:
            return {
                'provider': 'mercadopago',
                'access_token': gateway.access_token,
                'sandbox': gateway.is_sandbox,
            }

        # Legacy fallback: StoreIntegration
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

        # Credenciais da PLATAFORMA: opt-in explícito, nunca fallback silencioso.
        #
        # Sem esta trava, toda loja sem gateway próprio recebia o dinheiro do
        # cliente final na conta do dono da plataforma — intermediação de
        # pagamento de terceiro sem contrato, e a promessa "o PIX cai direto na
        # sua conta" virava mentira. Loja nova agora falha no cadastro (alto),
        # em vez de falhar no extrato (baixo).
        # A decisão é da LOJA, não de uma lista no .env. A allowlist por slug foi
        # a primeira tentativa e envelheceu mal em um dia: lista manual, invisível
        # no painel, e loja nova do dono nascia com pagamento bloqueado porque
        # ninguém lembrou de editar o ambiente.
        permitidas = set(getattr(settings, 'PLATFORM_GATEWAY_STORE_SLUGS', []) or [])
        da_plataforma = bool(
            getattr(store, 'usa_gateway_da_plataforma', False)
            or store.slug in permitidas
        )
        access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', None)
        if access_token and da_plataforma:
            return {
                'provider': 'mercadopago',
                'access_token': access_token,
                'sandbox': getattr(settings, 'MERCADO_PAGO_SANDBOX', False),
            }

        if access_token:
            logger.warning(
                '[checkout] Loja %s sem gateway próprio e sem usa_gateway_da_plataforma '
                '— pagamento bloqueado de propósito.',
                store.slug,
            )
        return None
    
    @staticmethod
    def create_payment(
        order: StoreOrder,
        payment_method: str = 'pix',
        payment_data: dict = None,
        amount=None,
        store: Store = None,
        description: str = None,
    ) -> dict:
        """Create a payment for an order using Mercado Pago.

        Fase 3 (Opção A): para PIX cria um StorePayment (fonte da verdade das
        cobranças) e espelha order.pix_* (compat storefront/print/bot).

        - `amount` opcional: valor da cobrança PIX (default = order.amount_due).
        - `order=None` + `store` + `amount`: cobrança AVULSA (sem pedido).
        - Idempotência: reusa StorePayment PENDING não-expirada (mesmo valor).
        """
        import mercadopago
        from decimal import Decimal
        from apps.stores.models import StorePayment

        # Loja-alvo: do pedido quando há order, senão o store explícito (avulso).
        target_store = order.store if order else store
        if target_store is None:
            raise ValueError("Loja obrigatoria para a cobranca")

        if payment_method == 'cash':
            if order is None:
                raise ValueError("Pagamento em dinheiro requer pedido")
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

        credentials = CheckoutService.get_payment_credentials(target_store)
        if not credentials:
            raise ValueError("Credenciais de pagamento nao configuradas")

        # Timeout explícito: o default (60s x 3 retries) pode segurar o worker
        # do checkout por minutos se o MP pendurar.
        from mercadopago.config import RequestOptions
        sdk = mercadopago.SDK(
            credentials['access_token'],
            request_options=RequestOptions(connection_timeout=20.0, max_retries=2),
        )
        payment_payload = payment_data or {}
        # payer_email para os fluxos baseados em pedido (cartão). PIX recomputa
        # o seu próprio (suporta avulso sem order).
        payer_email = get_valid_email_for_payment(order) if order is not None else None

        if payment_method == 'pix':
            # Valor da cobrança: explícito > amount_due do pedido. Avulso exige amount.
            if amount is None:
                if order is None:
                    raise ValueError("Valor obrigatorio para cobranca avulsa")
                amount = order.amount_due
            amount = Decimal(str(amount)).quantize(Decimal('0.01'))
            if amount <= Decimal('0.00'):
                raise ValueError("Valor da cobranca deve ser maior que zero")

            # Idempotência: reusa cobrança PIX pendente não-expirada de mesmo valor.
            existing = StorePayment.objects.filter(
                order=order,
                store=target_store,
                payment_method=StorePayment.PaymentMethod.PIX,
                status=StorePayment.PaymentStatus.PENDING,
                amount=amount,
            ).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
            ).order_by('-created_at').first()
            if existing:
                return {
                    'success': True,
                    'payment_id': existing.external_id,
                    'status': 'pending',
                    'payment_method': 'pix',
                    'pix_code': existing.qr_code,
                    'pix_qr_code': existing.qr_code_base64,
                    'ticket_url': existing.ticket_url,
                    'amount': str(existing.amount),
                    'payment_db_id': str(existing.id),
                    'pix_recipient_name': getattr(settings, 'MERCADO_PAGO_RECIPIENT_NAME', ''),
                    'requires_redirect': False,
                    'reused': True,
                }

            if order is not None:
                payer_email = get_valid_email_for_payment(order)
                name = order.customer_name or 'Cliente'
                mp_description = f"Pedido #{order.order_number} - {target_store.name}"
                external_reference = str(order.id)
            else:
                payer_email = (
                    payment_payload.get('payer_email')
                    or (target_store.owner.email if target_store.owner else None)
                    or 'cliente@noreply.com'
                )
                name = payment_payload.get('payer_name') or 'Cliente'
                mp_description = description or f"Cobranca - {target_store.name}"
                external_reference = f"avulso:{target_store.id}"
            logger.info(f"Using email for payment: {payer_email}")

            # PIX pela Orders API (/v1/orders), o mesmo caminho do cartão desde
            # 17/06. A rota antiga (/v1/payments) responde 403 PolicyAgent para
            # aplicações registradas como "Checkout Transparente via Orders" —
            # foi o que derrubou o PIX de todas as lojas em 19/08.
            from apps.stores.services import mp_orders

            if order is not None:
                order_payload = mp_orders.build_pix_order_payload(
                    order, payer_email, payment_payload, amount=amount,
                )
            else:
                # Cobrança avulsa: sem pedido não há itens nem endereço.
                first_name, last_name = mp_orders.split_name(name)
                order_payload = {
                    'type': 'online',
                    'processing_mode': 'automatic',
                    'total_amount': str(amount),
                    'external_reference': external_reference,
                    'description': mp_description[:256],
                    'payer': {
                        'email': payer_email,
                        'first_name': first_name,
                        'last_name': last_name,
                    },
                    'transactions': {'payments': [{
                        'amount': str(amount),
                        'payment_method': {'id': 'pix', 'type': 'bank_transfer'},
                    }]},
                }

            status_code, body = mp_orders.create_order(
                credentials['access_token'], order_payload,
            )
            pix_criado, _status_pix, _pix_id, _detalhe = mp_orders.interpret(status_code, body)
            result = {"status": status_code, "response": body}

            if pix_criado:
                dados_pix = mp_orders.extract_pix(body)
                # `_status_pix` vem do interpret(): action_required/pending → 'pending'.
                payment = {"id": dados_pix.get("payment_id"), "status": _status_pix}
                pix_data = {
                    "qr_code": dados_pix.get("qr_code", ""),
                    "qr_code_base64": dados_pix.get("qr_code_base64", ""),
                    "ticket_url": dados_pix.get("ticket_url", ""),
                    "expiration_date": dados_pix.get("date_of_expiration"),
                }
                expires_at = timezone.now() + timedelta(hours=24)

                # StorePayment é a fonte da verdade da cobrança.
                store_payment = StorePayment.objects.create(
                    order=order,
                    store=target_store,
                    amount=amount,
                    payment_method=StorePayment.PaymentMethod.PIX,
                    status=StorePayment.PaymentStatus.PENDING,
                    external_id=str(payment["id"]),
                    external_reference=external_reference,
                    qr_code=pix_data.get("qr_code", ""),
                    qr_code_base64=pix_data.get("qr_code_base64", ""),
                    ticket_url=pix_data.get("ticket_url", ""),
                    payer_email=payer_email or "",
                    payer_name=name,
                    expires_at=expires_at,
                )

                # Espelho no pedido (cobrança ativa) — compat storefront/print/bot.
                if order is not None:
                    order.payment_id = str(payment["id"])
                    order.payment_method = 'pix'
                    order.payment_status = StoreOrder.PaymentStatus.PENDING
                    order.pix_code = pix_data.get("qr_code", "")
                    order.pix_qr_code = pix_data.get("qr_code_base64", "")
                    order.pix_ticket_url = pix_data.get("ticket_url", "")
                    order.pix_expires_at = expires_at
                    order.save(update_fields=[
                        'payment_id',
                        'payment_method',
                        'payment_status',
                        'pix_code',
                        'pix_qr_code',
                        'pix_ticket_url',
                        'pix_expires_at',
                        'updated_at',
                    ])

                return {
                    'success': True,
                    'payment_id': payment["id"],
                    'status': payment["status"],
                    'payment_method': 'pix',
                    'pix_code': store_payment.qr_code,
                    'pix_qr_code': store_payment.qr_code_base64,
                    'ticket_url': store_payment.ticket_url,
                    'amount': str(amount),
                    'payment_db_id': str(store_payment.id),
                    'pix_recipient_name': getattr(settings, 'MERCADO_PAGO_RECIPIENT_NAME', ''),
                    'expiration': pix_data.get("expiration_date"),
                    'requires_redirect': False,
                }

            logger.error(f"Payment creation failed: {result}")

            # PIX recusado NÃO quer dizer "não dá pra pagar". Em 19/08 o MP
            # passou a devolver 403 PolicyAgent em POST /v1/payments (conta
            # bloqueada, chaves revogadas) enquanto o Checkout Pro seguia
            # criando cobrança normalmente. Sem este desvio o cliente via
            # "pagamento falhou" sem nenhuma forma de pagar, e a venda morria
            # com o pedido já criado no painel do lojista.
            try:
                fallback = CheckoutService.create_payment(
                    order,
                    payment_method='link',
                    payment_data=payment_payload,
                    amount=amount,
                    store=target_store,
                    description=description,
                )
            except Exception as exc:
                logger.warning("Fallback PIX->link falhou: %s", exc)
                fallback = None

            if fallback and fallback.get('success'):
                logger.info(
                    "PIX recusado pelo MP; cobranca seguiu por link de pagamento (pedido %s)",
                    order.order_number if order is not None else 'avulso',
                )
                fallback['pix_fallback'] = True
                return fallback

            # Honesto sem ser destrutivo: `payment_status=FAILED` já impede o
            # pedido de fingir cobrança ativa. Mexer no `status` era o que
            # sumia com a venda da tela de quem está trabalhando — foi o susto
            # do pedido da Aline em 11/ago, pelo caminho do cartão.
            if order is not None:
                order.payment_status = StoreOrder.PaymentStatus.FAILED
                order.save(update_fields=['payment_status', 'updated_at'])
                CheckoutService._release_coupon(order)
            corpo_erro = result.get("response", {}) or {}
            erros = corpo_erro.get("errors") or []
            mensagem = (
                (erros[0] or {}).get("message") if isinstance(erros, list) and erros
                else corpo_erro.get("message")
            )
            return {
                'success': False,
                'error': mensagem or "Erro ao criar pagamento",
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

                # Orders API (Checkout Transparente via Orders) — payload rico do
                # pedido real (itens, pagador, endereço, statement_descriptor, device_id).
                from apps.stores.services import mp_orders
                device_id = (
                    payment_payload.get('device_id')
                    or payment_payload.get('deviceId')
                    or payment_payload.get('device_session_id')
                )
                payment_type = 'debit_card' if payment_method == 'debit_card' else 'credit_card'
                order_payload = mp_orders.build_order_payload(
                    order,
                    card_token=card_token,
                    payment_method_id=payment_method_id,
                    installments=max(1, installments),
                    payer_email=payer_data.get('email') or payer_email,
                    payer_data={
                        'identification_type': identification_type,
                        'identification_number': identification_number,
                    },
                    payment_type=payment_type,
                )
                status_code, body = mp_orders.create_order(
                    credentials['access_token'], order_payload, device_id=device_id,
                )
                ok, mapped_status, pay_id, status_detail = mp_orders.interpret(status_code, body)

                if ok:
                    order.payment_id = pay_id or str(body.get('id', ''))
                    order.payment_method = payment_method
                    if mapped_status == 'approved':
                        order.status = StoreOrder.OrderStatus.CONFIRMED
                        order.payment_status = StoreOrder.PaymentStatus.PAID
                        order.paid_at = timezone.now()
                        if not order.confirmed_at:
                            order.confirmed_at = timezone.now()
                    else:  # pending / action_required
                        order.payment_status = StoreOrder.PaymentStatus.PENDING
                    order.save()
                    if mapped_status == 'approved':
                        try:
                            from apps.stores.services.loyalty_service import LoyaltyService
                            LoyaltyService.credit_order(order)
                        except Exception:
                            logger.warning('Falha ao creditar fidelidade do pedido %s', order.id, exc_info=True)

                    return {
                        'success': True,
                        'payment_id': order.payment_id,
                        'status': 'approved' if mapped_status == 'approved' else 'pending',
                        'status_detail': status_detail,
                        'payment_method': payment_method,
                        'requires_redirect': False,
                    }

                # O pedido NUNCA vira FAILED por causa do pagamento: em 11/ago
                # o pedido da Aline (R$ 270,37) apareceu no painel e sumiu um
                # segundo depois, e para a dona da loja foi como se alguém
                # tivesse excluído a venda. Cartão recusado é venda a
                # recuperar — quem conta essa história é o `payment_status`.
                if mp_orders.eh_erro_de_payload(status_code, body):
                    # Erro NOSSO de formato: o cartão nem foi consultado. Marcar
                    # o pagamento como falho seria mentira no histórico.
                    logger.error(
                        'Orders API recusou nosso payload (pedido %s): %s %s',
                        order.order_number, status_code, body,
                        extra={'payment.payload_error': True, 'order_id': str(order.id)},
                    )
                    order.payment_status = StoreOrder.PaymentStatus.PENDING
                    order.save(update_fields=['payment_status', 'updated_at'])
                    CheckoutService._release_coupon(order)
                    return {
                        'success': False,
                        'error': (
                            'Não conseguimos enviar o pagamento ao Mercado Pago. '
                            'O pedido foi mantido — tente outra forma de pagamento.'
                        ),
                    }

                logger.error(f"Orders API card payment failed: {status_code} {body}")
                order.payment_status = StoreOrder.PaymentStatus.FAILED
                order.save(update_fields=['payment_status', 'updated_at'])
                CheckoutService._release_coupon(order)
                return {
                    'success': False,
                    'error': status_detail or 'Erro ao processar pagamento com cartao',
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

            # Antifraude: mesma preference rica do link (payer completo, itens
            # reais quando a soma bate, statement_descriptor).
            from apps.stores.services import mp_orders
            card_total = Decimal(str(order.total)).quantize(Decimal('0.01'))
            card_items = mp_orders.build_preference_items(order)
            card_items_sum = sum(
                (Decimal(str(i['unit_price'])) * i['quantity'] for i in card_items),
                Decimal('0.00'),
            )
            if not card_items or card_items_sum.quantize(Decimal('0.01')) != card_total:
                card_items = [{
                    "title": f"Pedido #{order.order_number}",
                    "quantity": 1,
                    "unit_price": float(order.total),
                    "currency_id": "BRL",
                }]

            preference_data = {
                "items": card_items,
                "payer": mp_orders.build_preference_payer(
                    order, payer_email, document=identification_number,
                ),
                "statement_descriptor": mp_orders.statement_descriptor(order.store),
                "metadata": {
                    "store_slug": order.store.slug,
                    "order_id": str(order.id),
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

        if payment_method == 'link':
            # Link de pagamento (Checkout Pro / preference): página hospedada onde
            # o cliente escolhe cartão/PIX/boleto. Funciona avulso (sem pedido) ou
            # sobre um pedido. O payment id real só existe quando o cliente paga —
            # por isso a cobrança guarda o preference id em external_id e um
            # external_reference único (`splink:<token>`) pra o webhook reconciliar.
            import uuid

            if amount is None:
                if order is None:
                    raise ValueError("Valor obrigatorio para link avulso")
                amount = order.amount_due
            amount = Decimal(str(amount)).quantize(Decimal('0.01'))
            if amount <= Decimal('0.00'):
                raise ValueError("Valor da cobranca deve ser maior que zero")

            from apps.stores.services import mp_orders

            # Antifraude: preference rica (payer real, itens, statement_descriptor)
            # derruba o cc_rejected_high_risk. NUNCA usar o e-mail do dono como
            # payer — o MP lê como auto-pagamento (red flag de fraude).
            payer_block = None
            if order is not None:
                link_payer_email = get_valid_email_for_payment(order)
                link_payer_name = order.customer_name or 'Cliente'
                mp_title = f"Pedido #{order.order_number} - {target_store.name}"
                payer_block = mp_orders.build_preference_payer(
                    order, link_payer_email,
                    document=payment_payload.get('payer_document'),
                )
                mp_items = mp_orders.build_preference_items(order)
            else:
                link_payer_email = (payment_payload.get('payer_email') or '').strip() or None
                link_payer_name = payment_payload.get('payer_name') or 'Cliente'
                mp_title = description or f"Cobranca - {target_store.name}"
                mp_items = []
                doc = mp_orders.clean_document(payment_payload.get('payer_document'))
                if link_payer_email or doc:
                    # Sem dados, melhor NÃO mandar payer: o Checkout Pro coleta
                    # os dados reais do comprador (melhor pro antifraude).
                    payer_block = {}
                    if link_payer_email:
                        payer_block['email'] = link_payer_email
                    if payment_payload.get('payer_name'):
                        first, last = mp_orders.split_name(link_payer_name)
                        payer_block['name'] = first
                        payer_block['surname'] = last
                    if doc:
                        payer_block['identification'] = {'type': 'CPF', 'number': doc}

            # A preference cobra a SOMA dos itens: só usa itens reais quando a
            # soma bate com o valor da cobrança (taxa/desconto divergem → item único).
            items_sum = sum(
                (Decimal(str(i['unit_price'])) * i['quantity'] for i in mp_items),
                Decimal('0.00'),
            )
            if not mp_items or items_sum.quantize(Decimal('0.01')) != amount:
                mp_items = [{
                    "title": mp_title,
                    "quantity": 1,
                    "unit_price": float(amount),
                    "currency_id": "BRL",
                }]

            external_reference = f"splink:{uuid.uuid4().hex}"
            storefront_base_url = CheckoutService.get_storefront_base_url(target_store, payment_payload)
            # notification_url COM slug: o webhook resolve a loja (credenciais) pela
            # URL, já que a cobrança-link não casa por external_id antes do pagto.
            notification_url = f"{settings.BASE_URL}/webhooks/payments/mercadopago/{target_store.slug}/"

            preference_data = {
                "items": mp_items,
                "external_reference": external_reference,
                "statement_descriptor": mp_orders.statement_descriptor(target_store),
                "metadata": {
                    "store_slug": target_store.slug,
                    **({"order_id": str(order.id)} if order is not None else {}),
                },
                "back_urls": {
                    "success": f"{storefront_base_url}/sucesso",
                    "failure": f"{storefront_base_url}/erro",
                    "pending": f"{storefront_base_url}/pendente",
                },
                "auto_return": "approved",
                "notification_url": notification_url,
            }
            if payer_block:
                preference_data["payer"] = payer_block

            result = sdk.preference().create(preference_data)

            if result["status"] == 201:
                preference = result["response"]
                init_point = preference.get("init_point")

                store_payment = StorePayment.objects.create(
                    order=order,
                    store=target_store,
                    amount=amount,
                    payment_method=StorePayment.PaymentMethod.OTHER,
                    status=StorePayment.PaymentStatus.PENDING,
                    external_id=str(preference["id"]),
                    external_reference=external_reference,
                    payment_url=init_point or "",
                    payer_email=link_payer_email or "",
                    payer_name=link_payer_name,
                    # A descrição ia só para o título da preference no MP. Sem
                    # ela aqui, a lista de cobranças do painel é uma pilha de
                    # valores sem rótulo e o lojista não sabe qual link é de quem.
                    metadata=({'description': description} if description else {}),
                )

                if order is not None:
                    order.payment_preference_id = preference["id"]
                    order.payment_status = StoreOrder.PaymentStatus.PENDING
                    order.save(update_fields=[
                        'payment_preference_id',
                        'payment_status',
                        'updated_at',
                    ])

                return {
                    'success': True,
                    'payment_method': 'link',
                    'status': 'pending',
                    'payment_url': init_point,
                    'init_point': init_point,
                    'sandbox_init_point': preference.get('sandbox_init_point'),
                    'preference_id': preference['id'],
                    'payment_db_id': str(store_payment.id),
                    'amount': str(amount),
                    'requires_redirect': True,
                }

            logger.error(f"Link preference creation failed: {result}")
            return {
                'success': False,
                'error': result.get('response', {}).get('message', 'Erro ao criar link de pagamento'),
            }

        raise ValueError(f"Metodo de pagamento nao suportado: {payment_method}")

    @staticmethod
    @transaction.atomic
    def process_payment_webhook(payment_id: str, status: str, external_reference: str = None) -> StoreOrder:
        """Process payment webhook and update order/charge status.

        Fase 3 (Opção A): casa primeiro o StorePayment por external_id
        (multi-charge nativo). Mantém o FALLBACK LEGADO por order.payment_id
        para pedidos antigos sem StorePayment (prod cobra de verdade desde
        17/jun — não pode regressar).

        Link de pagamento: a cobrança-link guarda o preference id em external_id
        (o payment id real só existe quando o cliente paga). Casa pelo
        external_reference único (`splink:<token>`) e grava o payment id.
        """
        from apps.stores.models import StorePayment

        store_payment = StorePayment.objects.select_for_update().filter(
            external_id=str(payment_id)
        ).order_by('-created_at').first()

        if store_payment is None and external_reference and str(external_reference).startswith('splink:'):
            store_payment = StorePayment.objects.select_for_update().filter(
                external_reference=str(external_reference)
            ).order_by('-created_at').first()
            if store_payment is not None and store_payment.external_id != str(payment_id):
                store_payment.external_id = str(payment_id)
                store_payment.save(update_fields=['external_id', 'updated_at'])

        if store_payment is not None:
            return CheckoutService._handle_storepayment_webhook(store_payment, status)

        # Fallback legado: casa o pedido diretamente pelo payment_id.
        order = StoreOrder.objects.select_for_update().filter(
            payment_id=str(payment_id)
        ).first()

        if not order:
            logger.warning(f"Order not found for payment {payment_id}")
            return None

        return CheckoutService._apply_order_webhook_status(order, status)


    @staticmethod
    def _venda_de_cobranca_avulsa(store_payment):
        """Cria o pedido de uma cobrança avulsa que foi paga.

        Nasce PAGO: nascer pendente faria o dono cobrar de novo quem já pagou.
        E carrega `metadata['origem']` porque, sem isso, vira um pedido fantasma
        que ninguém sabe explicar de onde veio.

        IDENTIDADE (15/ago). Marcar a origem no metadata não bastou: o dono
        abriu a página de pedidos e viu "um pedido que só tem o valor". O
        pedido nascia sem UMA linha de item, sem nome de cliente, com
        `source` caindo em 'web' e `delivery_method` no default 'delivery' —
        ou seja, a comanda imprimia "*** ENTREGA ***" para uma cobrança que
        não tem para onde ir, e o relatório por canal creditava o site.

        Aqui a cobrança é de valor arbitrário: não existe produto de catálogo
        para apontar. Mas existe o que foi cobrado — descrição, valor, uma
        unidade. É isso que vira a linha, com `product` NULO de propósito:
        inventar um item do cardápio sujaria estoque e ranking de vendas.
        """
        from apps.stores.models import StoreOrder, StoreOrderItem

        # A cobrança pode ser reprocessada (o Mercado Pago reentrega webhook);
        # sem esta guarda, cada reentrega criaria um pedido novo.
        store_payment.refresh_from_db()
        if store_payment.order_id:
            return store_payment.order

        descricao = str(
            (store_payment.metadata or {}).get('description') or ''
        ).strip() or 'Cobrança por link de pagamento'

        order = StoreOrder.objects.create(
            store=store_payment.store,
            total=store_payment.amount,
            subtotal=store_payment.amount,
            status=StoreOrder.OrderStatus.CONFIRMED,
            payment_status=StoreOrder.PaymentStatus.PAID,
            payment_method=store_payment.payment_method or 'other',
            paid_at=store_payment.paid_at or timezone.now(),
            # Sem nome, a linha da lista fica indistinguível de pedido corrompido.
            customer_name=store_payment.payer_name or 'Cliente do link',
            customer_email=store_payment.payer_email or '',
            # `source` é a coluna que o BI agrupa; `metadata['origem']` ninguém
            # agrupa. Enquanto os dois discordavam, a tela de canais mentia.
            source='payment_link',
            # 'digital': não há endereço nem retirada combinada — é dinheiro
            # que entrou por um link, e a comanda precisa dizer isso.
            delivery_method=StoreOrder.DeliveryMethod.DIGITAL,
            metadata={
                'origem': 'link_de_pagamento',
                'store_payment_id': str(store_payment.id),
            },
        )
        StoreOrderItem.objects.create(
            order=order,
            product=None,
            product_name=descricao,
            unit_price=store_payment.amount,
            quantity=1,
            subtotal=store_payment.amount,
        )
        store_payment.order = order
        store_payment.save(update_fields=['order', 'updated_at'])
        logger.info(
            '[checkout] cobrança avulsa %s virou o pedido %s',
            store_payment.id, order.order_number,
        )
        return order

    @staticmethod
    def _handle_storepayment_webhook(store_payment, status: str):
        """Atualiza UMA cobrança (StorePayment) e reconcilia o pedido.

        - approved: marca a cobrança completed; pedido só vira paid quando
          amount_paid >= total (parcial fica PROCESSING). Avulso (order=None)
          só marca a cobrança.
        - rejected/cancelled/refunded/pending/in_process: atualiza a cobrança;
          aplica a transição legada no pedido apenas quando NÃO há outra
          cobrança já completed (preserva o fluxo single-charge de produção).
        """
        from apps.stores.models import StorePayment

        _MAP = {
            'approved': StorePayment.PaymentStatus.COMPLETED,
            'pending': StorePayment.PaymentStatus.PENDING,
            'in_process': StorePayment.PaymentStatus.PROCESSING,
            'rejected': StorePayment.PaymentStatus.FAILED,
            'cancelled': StorePayment.PaymentStatus.CANCELLED,
            'refunded': StorePayment.PaymentStatus.REFUNDED,
        }
        target = _MAP.get(status)
        if target is None:
            return store_payment.order

        order = store_payment.order

        if status == 'approved':
            # Idempotência: cobrança já confirmada → não reprocessa.
            if store_payment.status == StorePayment.PaymentStatus.COMPLETED:
                return order
            store_payment.status = StorePayment.PaymentStatus.COMPLETED
            if not store_payment.paid_at:
                store_payment.paid_at = timezone.now()
            store_payment.save()  # _sync_with_order espelha pix/paid_at (se houver order)

            if (store_payment.external_reference or "").startswith("subpix:"):
                from apps.stores.services import pix_billing_service
                pix_billing_service.apply_invoice_paid(store_payment)

            if order is None:
                # Cobrança avulsa PAGA vira venda.
                #
                # Antes o código parava aqui — o docstring dizia "avulso só marca
                # a cobrança" — e o dinheiro entrava sem virar pedido. Como
                # faturamento se conta por pedido, a venda simplesmente não
                # aparecia: em 14/ago eram 2 cobranças completed sem pedido,
                # R$ 249,01, dinheiro real invisível no relatório.
                #
                # Só no APPROVED: cobrança gerada e não paga é orçamento, e
                # contá-la inflaria o faturamento com dinheiro que nunca entrou
                # (havia 8 links pendentes que ninguém chegou a pagar).
                return CheckoutService._venda_de_cobranca_avulsa(store_payment)

            order.refresh_from_db()
            if order.amount_paid >= order.total:
                # Totalmente pago → confirma o pedido (email/pixel/etc).
                return CheckoutService._apply_order_webhook_status(order, 'approved')
            # Parcial: ainda falta receber — não marca pago.
            order.payment_status = StoreOrder.PaymentStatus.PROCESSING
            order.paid_at = None
            order.save(update_fields=['payment_status', 'paid_at', 'updated_at'])
            return order

        # Demais status: atualiza a cobrança.
        store_payment.status = target
        store_payment.save()

        if order is None:
            return None

        order.refresh_from_db()
        # Se já há outra cobrança confirmada, não derruba o pedido por causa de
        # uma cobrança extra rejeitada/estornada.
        if order.payments.filter(status=StorePayment.PaymentStatus.COMPLETED).exists():
            return order
        return CheckoutService._apply_order_webhook_status(order, status)

    @staticmethod
    def _apply_order_webhook_status(order: StoreOrder, status: str) -> StoreOrder:
        """Transições de status no PEDIDO a partir do status do gateway.

        Lógica legada (single-charge) preservada — usada tanto pelo fallback
        legado quanto pela reconciliação de StorePayment.
        """
        old_status = order.status
        # Estados em que o estoque já foi devolvido — evita restaurar 2x em webhooks repetidos.
        _STOCK_RESTORED_STATUSES = {
            StoreOrder.OrderStatus.CANCELLED,
            StoreOrder.OrderStatus.REFUNDED,
        }

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
            # O gateway manda no que é dele — a cobrança. Ele NÃO manda numa
            # venda já paga por outro meio (maquininha, dinheiro, PIX na mão)
            # nem numa comida que já saiu para o cliente.
            #
            # Em 19/08 quatro cobranças órfãs do CE-2608190245 foram canceladas
            # no MP; o pedido estava entregue e pago na maquininha, e o webhook
            # `cancelled` rebaixou a venda inteira para cancelled/failed —
            # sumindo com ela da tela de quem estava trabalhando. A trava que
            # existia só cobria "há outra cobrança COMPLETED no gateway", e
            # pagamento fora do gateway não produz StorePayment nenhum.
            #
            # Estorno (`refunded`) segue passando: ali existe decisão do lojista
            # sobre dinheiro que entrou de verdade.
            if (
                order.payment_status == StoreOrder.PaymentStatus.PAID
                or order.status in {
                    StoreOrder.OrderStatus.DELIVERED,
                    StoreOrder.OrderStatus.COMPLETED,
                }
            ):
                logger.info(
                    "Webhook '%s' ignorado para %s: venda já %s (pagamento=%s). "
                    "Cobrança cancelada não derruba venda entregue/paga.",
                    status, order.order_number, order.status, order.payment_status,
                )
                return order

            order.status = StoreOrder.OrderStatus.CANCELLED
            order.payment_status = StoreOrder.PaymentStatus.FAILED
            order.cancelled_at = timezone.now()
            update_fields.extend(['status', 'payment_status', 'cancelled_at'])
            # Só restaura estoque na PRIMEIRA transição para cancelado/estornado.
            # MP reenvia webhooks (cada um com id próprio, o dedup não pega), e
            # restaurar de novo infla o estoque -> overselling. Guard por old_status.
            if old_status not in _STOCK_RESTORED_STATUSES:
                CheckoutService._restore_stock(order)
                CheckoutService._release_coupon(order)
            trigger_order_email_automation(order, 'order_cancelled')

        elif status == 'refunded':
            order.status = StoreOrder.OrderStatus.REFUNDED
            order.payment_status = StoreOrder.PaymentStatus.REFUNDED
            order.cancelled_at = timezone.now()
            update_fields.extend(['status', 'payment_status', 'cancelled_at'])
            if old_status not in _STOCK_RESTORED_STATUSES:
                CheckoutService._restore_stock(order)

        else:
            return order

        order.save(update_fields=list(dict.fromkeys(update_fields)))

        if status == 'approved':
            try:
                from apps.stores.services.loyalty_service import LoyaltyService
                LoyaltyService.credit_order(order)
            except Exception:
                logger.warning('Falha ao creditar fidelidade do pedido %s', order.id, exc_info=True)
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

    @staticmethod
    def _release_coupon(order: StoreOrder):
        """Devolve a vaga do cupom quando o pedido morre (falhou/cancelado).

        A reserva é feita no checkout, antes do pagamento (ver
        `_create_order_atomic`). Sem esta devolução, cada tentativa frustrada
        consome uma unidade do `usage_limit` para sempre.

        Idempotente via `metadata['coupon_released']`: o Mercado Pago reenvia
        webhooks, e um segundo release devolveria uma vaga que não existe.
        """
        if not order.coupon_code or order.discount <= 0:
            return
        metadata = dict(order.metadata or {})
        if metadata.get('coupon_released'):
            return

        coupon = StoreCoupon.objects.filter(
            store=order.store, code__iexact=order.coupon_code
        ).first()
        if not coupon:
            return

        coupon.decrement_usage()
        metadata['coupon_released'] = True
        order.metadata = metadata
        order.save(update_fields=['metadata', 'updated_at'])


# Singleton instance
checkout_service = CheckoutService()
