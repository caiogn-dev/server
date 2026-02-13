"""
Store order models - StoreOrder, StoreOrderItem, StoreOrderComboItem.
"""
import uuid
import logging
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel
from apps.whatsapp.utils import get_default_whatsapp_account
from .base import Store

logger = logging.getLogger(__name__)
User = get_user_model()


class StoreOrder(BaseModel):
    """
    Order model for any store.
    Comprehensive order tracking with payment and delivery integration.
    """

    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PROCESSING = 'processing', 'Processing'
        PAID = 'paid', 'Paid'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready for Pickup/Delivery'
        SHIPPED = 'shipped', 'Shipped'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'
        FAILED = 'failed', 'Failed'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        PARTIALLY_REFUNDED = 'partially_refunded', 'Partially Refunded'

    class DeliveryMethod(models.TextChoices):
        DELIVERY = 'delivery', 'Delivery'
        PICKUP = 'pickup', 'Pickup'
        DIGITAL = 'digital', 'Digital Delivery'

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='orders'
    )

    # Order number
    order_number = models.CharField(max_length=50, unique=True, db_index=True)

    # Security token for public access
    access_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default='',
        blank=True,
        help_text='Secure token for public order access'
    )

    # Customer
    customer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='store_orders'
    )
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)

    # Status
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )

    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=50, blank=True)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    # Payment
    payment_method = models.CharField(max_length=50, blank=True)
    payment_id = models.CharField(max_length=255, blank=True, db_index=True)
    payment_preference_id = models.CharField(max_length=255, blank=True)
    pix_code = models.TextField(blank=True)
    pix_qr_code = models.TextField(blank=True)
    pix_ticket_url = models.URLField(max_length=500, blank=True)

    # Delivery
    delivery_method = models.CharField(
        max_length=20,
        choices=DeliveryMethod.choices,
        default=DeliveryMethod.DELIVERY
    )
    delivery_address = models.JSONField(default=dict, blank=True)
    delivery_notes = models.TextField(blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_time = models.CharField(max_length=50, blank=True)

    # Tracking
    tracking_code = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)
    carrier = models.CharField(max_length=100, blank=True)

    # Notes
    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # Timestamps
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'store_orders'
        verbose_name = 'Store Order'
        verbose_name_plural = 'Store Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['store', 'payment_status']),
            models.Index(fields=['customer_phone']),
            models.Index(fields=['customer_email']),
        ]

    def __str__(self):
        return f"{self.store.name} - Order #{self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        if not self.access_token:
            self.access_token = self.generate_access_token()
        super().save(*args, **kwargs)

    def generate_order_number(self):
        """Generate unique order number."""
        import random
        import string
        prefix = self.store.slug[:3].upper() if self.store else 'ORD'
        timestamp = timezone.now().strftime('%y%m%d')
        random_suffix = ''.join(random.choices(string.digits, k=4))
        return f"{prefix}{timestamp}{random_suffix}"

    @staticmethod
    def generate_access_token():
        """Generate a secure random access token."""
        import secrets
        return secrets.token_urlsafe(32)

    def update_status(self, new_status: str, notify: bool = True):
        """Update order status and optionally send notifications."""
        old_status = self.status
        self.status = new_status

        if new_status == self.OrderStatus.PAID:
            self.paid_at = timezone.now()
            self.payment_status = self.PaymentStatus.PAID
        elif new_status == self.OrderStatus.SHIPPED:
            self.shipped_at = timezone.now()
        elif new_status == self.OrderStatus.DELIVERED:
            self.delivered_at = timezone.now()
        elif new_status == self.OrderStatus.CANCELLED:
            self.cancelled_at = timezone.now()

        self.save()

        if notify:
            self.send_status_webhook(old_status, new_status)
            self._trigger_status_email_automation(new_status)
            self._trigger_status_whatsapp_notification(new_status)

        return self

    def _trigger_status_email_automation(self, new_status: str):
        """Trigger email automation based on status change."""
        try:
            from apps.stores.services.checkout_service import trigger_order_email_automation

            status_trigger_map = {
                self.OrderStatus.CONFIRMED: 'order_confirmed',
                self.OrderStatus.PAID: 'payment_confirmed',
                self.OrderStatus.SHIPPED: 'order_shipped',
                self.OrderStatus.OUT_FOR_DELIVERY: 'order_shipped',
                self.OrderStatus.DELIVERED: 'order_delivered',
                self.OrderStatus.CANCELLED: 'order_cancelled',
            }

            trigger_type = status_trigger_map.get(new_status)
            if trigger_type:
                extra_context = {}
                if new_status in [self.OrderStatus.SHIPPED, self.OrderStatus.OUT_FOR_DELIVERY]:
                    extra_context = {
                        'tracking_code': self.tracking_code or '',
                        'tracking_url': self.tracking_url or '',
                        'carrier': self.carrier or '',
                    }
                trigger_order_email_automation(self, trigger_type, extra_context)
        except Exception as e:
            logger.error(f"Failed to trigger email automation for order {self.order_number}: {e}")

    def _trigger_status_whatsapp_notification(self, new_status: str):
        """Trigger WhatsApp notification based on status change."""
        if not self.customer_phone:
            return

        status_message_map = {
            self.OrderStatus.CONFIRMED: "✅ *Pedido Confirmado!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi confirmado!",
            self.OrderStatus.PAID: "💰 *Pagamento Confirmado!*\n\nOlá {customer_name}!\n\nO pagamento do pedido #{order_number} foi confirmado!",
            self.OrderStatus.PREPARING: "👨‍🍳 *Pedido em Preparo!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} está sendo preparado!",
            self.OrderStatus.READY: "📦 *Pedido Pronto!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} está pronto!",
            self.OrderStatus.SHIPPED: "🚚 *Pedido Enviado!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi enviado!",
            self.OrderStatus.DELIVERED: "📦 *Pedido Entregue!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi entregue!",
            self.OrderStatus.CANCELLED: "❌ *Pedido Cancelado*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi cancelado.",
        }

        message_template = status_message_map.get(new_status)
        if not message_template:
            return

        notification_key = f'whatsapp_notification_{new_status}'
        if self.metadata.get(notification_key):
            return

        try:
            message_text = message_template.format(
                customer_name=self.customer_name or 'Cliente',
                order_number=self.order_number,
            )

            phone = self._normalize_phone_number(self.customer_phone)
            if not phone:
                logger.warning(
                    f"Invalid phone number for WhatsApp notification (order {self.order_number})"
                )
                return

            from apps.whatsapp.services import MessageService

            # Use the new centralized method to get WhatsApp account
            account = None
            if self.store:
                account = self.store.get_whatsapp_account()
            
            # Fallback to default account only if no store-linked account found
            if not account:
                account = get_default_whatsapp_account(create_if_missing=False)

            if not account:
                logger.warning(f"No WhatsApp account found to notify order {self.order_number}")
                return
            if not account.phone_number_id:
                logger.warning(
                    f"WhatsApp account {account.id} missing phone_number_id for order {self.order_number}"
                )
                return

            message_service = MessageService()
            message_service.send_text_message(
                account_id=str(account.id),
                to=phone,
                text=message_text,
                metadata={
                    'source': 'store_order_notification',
                    'order_id': str(self.id),
                    'customer_name': self.customer_name or ''
                }
            )

            self.metadata[notification_key] = timezone.now().isoformat()
            self.save(update_fields=['metadata'])

        except Exception as e:
            logger.error(f"Failed to send WhatsApp notification for order {self.order_number}: {e}")

    def send_status_webhook(self, old_status: str, new_status: str):
        """Send webhook notification for status change."""
        try:
            from apps.stores.services import webhook_service

            event_map = {
                self.OrderStatus.CONFIRMED: 'order.updated',
                self.OrderStatus.PAID: 'order.paid',
                self.OrderStatus.SHIPPED: 'order.shipped',
                self.OrderStatus.DELIVERED: 'order.delivered',
                self.OrderStatus.CANCELLED: 'order.cancelled',
            }

            event = event_map.get(new_status, 'order.updated')
            webhook_service.trigger_webhooks(self.store, event, {
                'order_id': str(self.id),
                'order_number': self.order_number,
                'old_status': old_status,
                'new_status': new_status,
            })
        except Exception as e:
            logger.error(f"Failed to send webhook for order {self.order_number}: {e}")

    def _normalize_phone_number(self, raw_phone: str) -> str:
        """Ensure the phone number is digits-only and has the Brazil prefix."""
        from apps.core.utils import normalize_phone_number
        return normalize_phone_number(raw_phone or '')


class StoreOrderItem(models.Model):
    """Individual items in an order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        StoreOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )

    # Product reference
    product = models.ForeignKey(
        'stores.StoreProduct',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    variant = models.ForeignKey(
        'stores.StoreProductVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Denormalized product info
    product_name = models.CharField(max_length=255)
    variant_name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=100, blank=True)

    # Pricing
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    # Options
    options = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_order_items'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class StoreOrderComboItem(models.Model):
    """Combo item in an order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        StoreOrder,
        on_delete=models.CASCADE,
        related_name='combo_items'
    )

    combo = models.ForeignKey(
        'stores.StoreCombo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Denormalized combo info
    combo_name = models.CharField(max_length=255)

    # Pricing
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    # Customizations
    customizations = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_order_combo_items'
        verbose_name = 'Order Combo Item'
        verbose_name_plural = 'Order Combo Items'

    def __str__(self):
        return f"{self.quantity}x {self.combo_name}"

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)
