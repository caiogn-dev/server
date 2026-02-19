"""
Checkout Service - Unified checkout for all stores.
Handles order creation, payment processing, and stock management.
"""
import logging
import re
import uuid
from decimal import Decimal
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from apps.stores.models import (
    Store, StoreCart, StoreOrder, StoreOrderItem,
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
    
    # Fallback to a generic email
    return f"cliente{order.order_number}@pastita.com.br"


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
                'zone_name': 'Padrão',
                'estimated_minutes': 30,
                'estimated_days': 0,
            }
        
        distance = Decimal(str(distance_km))
        
        # Calculate fee: base + (distance - threshold) * per_km_rate
        if distance <= free_km_threshold:
            fee = base_fee
            zone_name = 'Próximo'
        else:
            extra_km = distance - free_km_threshold
            fee = base_fee + (extra_km * fee_per_km)
            
            # Determine zone name based on distance
            if distance <= 5:
                zone_name = 'Próximo'
            elif distance <= 10:
                zone_name = 'Padrão'
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
                return {'valid': False, 'error': 'Cupom não encontrado'}
            
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
        
        # Validate stock
        stock_errors = cart_service.validate_stock_for_checkout(cart)
        if stock_errors:
            raise ValueError(f"Erros de estoque: {stock_errors}")
        
        # Calculate delivery fee
        delivery_info = {'fee': Decimal('0'), 'zone_name': 'Retirada'}
        if delivery_data and delivery_data.get('method') == 'delivery':
            distance = delivery_data.get('distance_km')
            zip_code = delivery_data.get('zip_code')
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
        
        # Create order
        order = StoreOrder.objects.create(
            store=store,
            customer=cart.user,
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
                if delivery_data and delivery_data.get('method') == 'delivery'
                else StoreOrder.DeliveryMethod.PICKUP
            ),
            delivery_address=delivery_data.get('address', {}) if delivery_data else {},
            delivery_notes=delivery_data.get('notes', '') if delivery_data else '',
            customer_notes=notes,
            metadata={
                'delivery_zone': delivery_info.get('zone_name'),
                'estimated_minutes': delivery_info.get('estimated_minutes'),
            }
        )
        
        # Update user name from checkout data if provided
        if cart.user and customer_data.get('name'):
            full_name = customer_data['name'].strip()
            if full_name and (cart.user.first_name == 'Usuário' or not cart.user.first_name):
                name_parts = full_name.split(' ', 1)
                cart.user.first_name = name_parts[0]
                if len(name_parts) > 1:
                    cart.user.last_name = name_parts[1]
                cart.user.save(update_fields=['first_name', 'last_name'])
        
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
        
        # Handle combo items
        for combo_item in cart.combo_items.select_related('combo').all():
            # Create a single order item for the combo
            StoreOrderItem.objects.create(
                order=order,
                product=None,
                variant=None,
                product_name=f"Combo: {combo_item.combo.name}",
                variant_name='',
                sku='',
                unit_price=combo_item.combo.price,
                quantity=combo_item.quantity,
                subtotal=combo_item.subtotal,
                options=combo_item.customizations,
                notes=combo_item.notes,
            )
            
            # Decrement combo stock if tracked
            if combo_item.combo.track_stock:
                from apps.stores.models import StoreCombo
                StoreCombo.objects.filter(id=combo_item.combo.id).update(
                    stock_quantity=F('stock_quantity') - combo_item.quantity
                )
        
        # Mark coupon as used (atomic)
        if coupon:
            coupon.increment_usage()
        
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
    def create_payment(order: StoreOrder, payment_method: str = 'pix') -> dict:
        """Create a payment for an order using Mercado Pago."""
        import mercadopago
        
        # Handle cash payment - no Mercado Pago needed
        if payment_method == 'cash':
            order.payment_method = 'cash'
            order.status = StoreOrder.OrderStatus.PROCESSING
            order.save()
            
            return {
                'success': True,
                'payment_id': None,
                'status': 'pending',
                'payment_method': 'cash',
                'message': 'Pagamento em dinheiro na entrega/retirada'
            }
        
        credentials = CheckoutService.get_payment_credentials(order.store)
        if not credentials:
            raise ValueError("Credenciais de pagamento não configuradas")
        
        sdk = mercadopago.SDK(credentials['access_token'])
        
        # Get valid email for payment
        payer_email = get_valid_email_for_payment(order)
        logger.info(f"Using email for payment: {payer_email} (original: {order.customer_email})")
        
        # Build payment data
        if payment_method == 'pix':
            payment_data = {
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
            
            result = sdk.payment().create(payment_data)
            
            if result["status"] == 201:
                payment = result["response"]
                
                # Update order with payment info
                order.payment_id = str(payment["id"])
                order.payment_method = 'pix'
                order.status = StoreOrder.OrderStatus.PROCESSING
                
                # Get PIX data
                pix_data = payment.get("point_of_interaction", {}).get("transaction_data", {})
                order.pix_code = pix_data.get("qr_code", "")
                order.pix_qr_code = pix_data.get("qr_code_base64", "")
                
                # Get ticket_url (link to payment page with QR code)
                ticket_url = pix_data.get("ticket_url", "")
                order.pix_ticket_url = ticket_url
                
                logger.info(f"PIX data for order {order.order_number}: code_len={len(order.pix_code)}, qr_len={len(order.pix_qr_code)}, ticket_url={ticket_url}")
                
                order.save()
                
                return {
                    'success': True,
                    'payment_id': payment["id"],
                    'status': payment["status"],
                    'pix_code': order.pix_code,
                    'pix_qr_code': order.pix_qr_code,
                    'ticket_url': ticket_url,
                    'expiration': pix_data.get("expiration_date"),
                }
            else:
                logger.error(f"Payment creation failed: {result}")
                return {
                    'success': False,
                    'error': result.get("response", {}).get("message", "Erro ao criar pagamento"),
                }
        
        else:
            # Create preference for other payment methods
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
                    "success": f"{settings.FRONTEND_URL}/sucesso?order={order.id}",
                    "failure": f"{settings.FRONTEND_URL}/erro?order={order.id}",
                    "pending": f"{settings.FRONTEND_URL}/pendente?order={order.id}",
                },
                "auto_return": "approved",
                "notification_url": f"{settings.BASE_URL}/webhooks/payments/mercadopago/",
            }
            
            result = sdk.preference().create(preference_data)
            
            if result["status"] == 201:
                preference = result["response"]
                
                order.payment_preference_id = preference["id"]
                order.status = StoreOrder.OrderStatus.PROCESSING
                order.save()
                
                return {
                    'success': True,
                    'preference_id': preference["id"],
                    'init_point': preference["init_point"],
                    'sandbox_init_point': preference.get("sandbox_init_point"),
                }
            else:
                logger.error(f"Preference creation failed: {result}")
                return {
                    'success': False,
                    'error': result.get("response", {}).get("message", "Erro ao criar preferência"),
                }
    
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
        
        status_map = {
            'approved': (StoreOrder.OrderStatus.PAID, StoreOrder.PaymentStatus.PAID),
            'pending': (StoreOrder.OrderStatus.PROCESSING, StoreOrder.PaymentStatus.PROCESSING),
            'in_process': (StoreOrder.OrderStatus.PROCESSING, StoreOrder.PaymentStatus.PROCESSING),
            'rejected': (StoreOrder.OrderStatus.FAILED, StoreOrder.PaymentStatus.FAILED),
            'cancelled': (StoreOrder.OrderStatus.CANCELLED, StoreOrder.PaymentStatus.FAILED),
            'refunded': (StoreOrder.OrderStatus.REFUNDED, StoreOrder.PaymentStatus.REFUNDED),
        }
        
        if status in status_map:
            order_status, payment_status = status_map[status]
            order.status = order_status
            order.payment_status = payment_status
            
            if status == 'approved':
                order.paid_at = timezone.now()
                # Trigger payment confirmed email automation
                trigger_order_email_automation(order, 'payment_confirmed')
            elif status in ['cancelled', 'rejected', 'refunded']:
                order.cancelled_at = timezone.now()
                # Restore stock
                CheckoutService._restore_stock(order)
                # Trigger order cancelled email automation
                if status in ['cancelled', 'rejected']:
                    trigger_order_email_automation(order, 'order_cancelled')
            
            order.save()

            if status == 'approved':
                try:
                    from apps.stores.services.meta_pixel_service import send_purchase_event
                    send_purchase_event(order)
                except Exception as exc:
                    logger.warning(f"Meta Pixel CAPI failed for {order.order_number}: {exc}")

            # Trigger WhatsApp notification for status changes
            try:
                order._trigger_status_whatsapp_notification(order.status)
            except Exception as exc:
                logger.warning(f"WhatsApp notification failed for {order.order_number}: {exc}")
            
            logger.info(f"Order {order.order_number} status updated: {old_status} -> {order_status}")
        
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
