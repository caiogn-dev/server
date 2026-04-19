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
        import logging
        logger = logging.getLogger(__name__)
        
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
        
        Uses store metadata for configuration or sensible defaults.
        Fee structure:
        - Base fee (minimum)
        - Per-km rate after a threshold
        - Estimated time based on distance
        """
        # Get configuration from store metadata or use defaults
        metadata = store.metadata or {}
        base_fee = Decimal(str(metadata.get('delivery_base_fee', store.default_delivery_fee or 8.0)))
        fee_per_km = Decimal(str(metadata.get('delivery_fee_per_km', 1.0)))
        free_km_threshold = Decimal(str(metadata.get('delivery_free_km', 3.0)))
        max_fee = Decimal(str(metadata.get('delivery_max_fee', 25.0)))
        
        # If no distance provided, return base fee
        if distance_km is None:
            return {
                'fee': float(base_fee),
                'zone_name': 'Padrao',
                'estimated_minutes': 30,
                'estimated_days': 0,
            }
        
        distance = Decimal(str(distance_km))
        
        # Calculate fee: base + (distance - threshold) * per_km_rate
        if distance <= free_km_threshold:
            fee = base_fee
            zone_name = 'Proximo'
        else:
            extra_km = distance - free_km_threshold
            fee = base_fee + (extra_km * fee_per_km)
            
            # Determine zone name based on distance
            if distance <= 5:
                zone_name = 'Proximo'
            elif distance <= 10:
                zone_name = 'Padrao'
            elif distance <= 15:
                zone_name = 'Distante'
            else:
                zone_name = 'Muito Distante'
        
        # Cap at max fee
        fee = min(fee, max_fee)
        
        # Round to 2 decimal places
        fee = fee.quantize(Decimal('0.01'))
        
        # Estimate delivery time: ~3 min per km + 15 min preparation
        estimated_minutes = int(15 + (float(distance) * 3))
        
        return {
            'fee': float(fee),
            'zone_name': zone_name,
            'estimated_minutes': estimated_minutes,
            'estimated_days': 0,
            'distance_km': float(distance),
            'calculation': 'dynamic',
        }
    
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
        notes: str = ''
    ) -> StoreOrder:
        """
        Create an order from a cart with atomic stock decrement.
        """
        store = cart.store
        delivery_payload = dict(delivery_data or {})
        delivery_address = dict(delivery_payload.get('address') or {})

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
        delivery_info = {'fee': Decimal('0'), 'zone_name': 'Retirada'}
        if delivery_payload and delivery_payload.get('method') == 'delivery':
            distance = delivery_payload.get('distance_km')
            zip_code = delivery_payload.get('zip_code')
            delivery_info = CheckoutService.calculate_delivery_fee(
                store,
                distance_km=Decimal(str(distance)) if distance else None,
                zip_code=zip_code
            )
        
        delivery_fee = Decimal(str(delivery_info['fee']))
        
        # Calculate subtotal
        subtotal = Decimal('0')
        for item in cart.items.all():
            subtotal += item.subtotal
        for combo_item in cart.combo_items.all():
            subtotal += combo_item.subtotal
        
        # Validate and apply coupon using unified StoreCoupon model
        discount = Decimal('0')
        coupon = None
        if coupon_code:
            coupon_result = CheckoutService.validate_coupon(store, coupon_code, subtotal, user=cart.user)
            if coupon_result['valid']:
                discount = Decimal(str(coupon_result['discount']))
                coupon = StoreCoupon.objects.get(id=coupon_result['coupon_id'])
        
        # Calculate total (no tax - just subtotal + delivery - discount)
        total = subtotal + delivery_fee - discount

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
                'estimated_minutes': delivery_info.get('estimated_minutes'),
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

