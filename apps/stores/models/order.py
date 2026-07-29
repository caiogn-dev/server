"""
Store order models - StoreOrder, StoreOrderItem.
StoreOrderComboItem has been moved to order_combo_item.py.
"""
import uuid
import secrets
import logging
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel
from apps.whatsapp.utils import get_default_whatsapp_account
from .base import Store

logger = logging.getLogger(__name__)
User = get_user_model()


def build_loyalty_status_line(store, user):
    """Linha de fidelidade anexada à mensagem de pagamento confirmado ('' se n/a)."""
    if not user or not store:
        return ''
    from apps.stores.services.loyalty_service import LoyaltyService
    status = LoyaltyService.get_status(store, user)
    if not status.get('enabled'):
        return ''
    label, label_plural = LoyaltyService.item_labels(store)
    if status['available_rewards'] > 0:
        count = status['available_rewards']
        item_word = label if count == 1 else label_plural
        return f"\n\n🎁 Você tem {count} {item_word} grátis para resgatar!"
    if status['qualified_salads'] > 0:
        return (f"\n\n🎁 Cartão fidelidade: {status['progress']}/{status['threshold']} — "
                f"faltam {status['remaining']} para o próximo {label} grátis!")
    return ''


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
    customer_email = models.EmailField(blank=True)
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
    pix_expires_at = models.DateTimeField(null=True, blank=True)
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

    # External delivery provider (e.g. toca-delivery SaaS)
    external_delivery_provider = models.CharField(max_length=50, blank=True, default='')
    external_delivery_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    external_delivery_code = models.CharField(max_length=30, blank=True, default='')
    external_delivery_status = models.CharField(max_length=30, blank=True, default='')
    external_delivery_url = models.URLField(max_length=500, blank=True, default='')

    # Notes
    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # Timestamps for status tracking
    confirmed_at = models.DateTimeField(null=True, blank=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    out_for_delivery_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # PDV: desconto manual e acréscimo
    manual_discount_type = models.CharField(
        max_length=10,
        choices=[('percent', '%'), ('fixed', 'R$')],
        null=True,
        blank=True,
        verbose_name='Tipo de Desconto Manual',
    )
    manual_discount_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name='Valor do Desconto Manual',
    )
    manual_discount_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Motivo do Desconto',
    )
    surcharge_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name='Valor do Acréscimo',
    )
    surcharge_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Motivo do Acréscimo',
    )
    created_by_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_orders',
        verbose_name='Criado por (staff)',
    )

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    # Delivery provider tracking
    DELIVERY_PROVIDER_CHOICES = [
        ('none', 'None'),
        ('toca', 'Toca Delivery'),
        ('uber', 'Uber Eats'),
    ]
    delivery_provider = models.CharField(
        max_length=10,
        choices=DELIVERY_PROVIDER_CHOICES,
        default='none',
        db_index=True,
    )

    # Uber delivery fields
    uber_delivery_request_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Uber's delivery request ID",
    )
    uber_driver_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    uber_driver_name = models.CharField(
        max_length=255,
        blank=True,
    )
    uber_driver_phone = models.CharField(
        max_length=20,
        blank=True,
    )
    uber_vehicle_info = models.CharField(
        max_length=255,
        blank=True,
    )
    uber_eta_minutes = models.IntegerField(
        blank=True,
        null=True,
    )
    uber_pickup_instructions = models.TextField(
        blank=True,
    )
    uber_created_at = models.DateTimeField(
        blank=True,
        null=True,
    )

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
            models.Index(fields=['customer', 'store'], name='order_customer_store_idx'),
            models.Index(fields=['store', 'created_at'], name='order_store_created_idx'),
            # Dashboard filtra status + janela (pending/cancelled_7d) por loja.
            models.Index(fields=['store', 'status', 'created_at'], name='order_store_stat_created_idx'),
            models.Index(fields=['delivery_provider']),
            models.Index(fields=['uber_delivery_request_id']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(subtotal__gte=0), name='order_subtotal_gte_0'),
            models.CheckConstraint(condition=models.Q(discount__gte=0), name='order_discount_gte_0'),
            models.CheckConstraint(condition=models.Q(total__gte=0), name='order_total_gte_0'),
            models.CheckConstraint(condition=models.Q(delivery_fee__gte=0), name='order_delivery_fee_gte_0'),
            models.CheckConstraint(condition=models.Q(tax__gte=0), name='order_tax_gte_0'),
        ]

    def __str__(self):
        return f"{self.store.name} - Order #{self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        if not self.access_token:
            self.access_token = self.generate_access_token()
        super().save(*args, **kwargs)

    @property
    def amount_paid(self):
        """Total efetivamente recebido = soma dos StorePayment 'completed'.

        DERIVADO (sem campo físico) — fonte da verdade das cobranças é o
        StorePayment (Fase 3, Opção A). Usa a annotation `amount_paid_agg` do
        queryset quando presente (anti-N+1 em listas); senão agrega on-demand.
        """
        annotated = getattr(self, 'amount_paid_agg', None)
        if annotated is not None:
            return Decimal(annotated).quantize(Decimal('0.01'))
        total = self.payments.filter(status='completed').aggregate(
            t=models.Sum('amount')
        )['t']
        return (total or Decimal('0.00')).quantize(Decimal('0.01'))

    @property
    def amount_due(self):
        """Quanto ainda falta receber = max(0, total - amount_paid)."""
        due = (self.total or Decimal('0.00')) - self.amount_paid
        if due < Decimal('0.00'):
            due = Decimal('0.00')
        return due.quantize(Decimal('0.01'))

    @property
    def is_fully_paid(self):
        """True quando o recebido cobre o total do pedido."""
        return self.amount_paid >= (self.total or Decimal('0.00'))

    def recalculate_totals(self, save=True):
        """Fonte da verdade do total. Soma os itens em subtotal e aplica a
        fórmula canônica: total = subtotal - discount + tax + delivery_fee
        + surcharge_value, com piso em 0. Não aceita total do cliente."""
        from decimal import Decimal
        subtotal = sum((item.subtotal for item in self.items.all()), Decimal('0.00'))
        self.subtotal = subtotal
        total = (
            subtotal
            - (self.discount or Decimal('0.00'))
            + (self.tax or Decimal('0.00'))
            + (self.delivery_fee or Decimal('0.00'))
            + (self.surcharge_value or Decimal('0.00'))
        )
        if total < Decimal('0.00'):
            total = Decimal('0.00')
        self.total = total
        if save:
            self.save(update_fields=['subtotal', 'total', 'updated_at'])
        return self.total

    def generate_order_number(self):
        """Generate unique order number using CSPRNG suffix (10k possibilities)."""
        prefix = self.store.slug[:3].upper() if self.store else 'ORD'
        timestamp = timezone.now().strftime('%y%m%d')
        random_suffix = f'{secrets.randbelow(10000):04d}'
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

        # Set timestamp for each status
        if new_status == self.OrderStatus.CONFIRMED:
            self.confirmed_at = timezone.now()
        elif new_status == self.OrderStatus.PROCESSING:
            self.processing_at = timezone.now()
        elif new_status == self.OrderStatus.PAID:
            self.paid_at = timezone.now()
            self.payment_status = self.PaymentStatus.PAID
        elif new_status == self.OrderStatus.PREPARING:
            self.preparing_at = timezone.now()
        elif new_status == self.OrderStatus.READY:
            self.ready_at = timezone.now()
        elif new_status == self.OrderStatus.SHIPPED:
            self.shipped_at = timezone.now()
        elif new_status == self.OrderStatus.OUT_FOR_DELIVERY:
            self.out_for_delivery_at = timezone.now()
        elif new_status == self.OrderStatus.DELIVERED:
            self.delivered_at = timezone.now()
        elif new_status == self.OrderStatus.CANCELLED:
            self.cancelled_at = timezone.now()

        # Pagamento na entrega/retirada: pedidos em dinheiro nascem 'pending' e nunca
        # passam pelo status PAID; ao serem entregues/concluídos o dinheiro foi recebido
        # → marca pago p/ entrarem no faturamento (a receita filtra payment_status=paid,
        # então sem isto a venda em dinheiro zerava nos relatórios). NÃO toca pedidos
        # online (pix/cartão), que pagam via webhook antes da entrega.
        OFFLINE_PAYMENT_METHODS = {'cash'}
        RECEIVED_STATUSES = {self.OrderStatus.DELIVERED, self.OrderStatus.COMPLETED}
        if (
            new_status in RECEIVED_STATUSES
            and self.payment_method in OFFLINE_PAYMENT_METHODS
            and self.payment_status != self.PaymentStatus.PAID
        ):
            self.payment_status = self.PaymentStatus.PAID
            if not self.paid_at:
                self.paid_at = timezone.now()

        self.save()

        if notify:
            self.send_status_webhook(old_status, new_status)
            self._trigger_status_email_automation(new_status)
            # WhatsApp notification is dispatched via post_save signal → Celery task
            # (notify_order_status_change) to avoid duplicate sends. Do NOT call
            # _trigger_status_whatsapp_notification() here — it would fire twice
            # for stores that have AutoMessage templates configured.

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
        logger.info(f"[WhatsAppNotification] START - Order {self.order_number}, Status: {new_status}, notify_enabled={bool(new_status)}")
        
        if not self.customer_phone:
            logger.warning(f"[WhatsAppNotification] RETURN: No customer phone for order {self.order_number}")
            return

        default_message_map = {
            self.OrderStatus.PROCESSING: "⏳ *Pedido em Processamento!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} está sendo processado!",
            self.OrderStatus.CONFIRMED: "✅ *Pedido Confirmado!*\n\nOlá {customer_name}! Seu pedido #{order_number} foi confirmado e logo começaremos a preparar. 🙌",
            self.OrderStatus.PAID: "💰 *Pagamento Confirmado!*\n\nOlá {customer_name}!\n\nO pagamento do pedido #{order_number} foi confirmado!",
            self.OrderStatus.PREPARING: "👨‍🍳 *Seu pedido está sendo preparado!*\n\nOlá {customer_name}! O pedido #{order_number} está na cozinha. Em breve estará pronto!",
            self.OrderStatus.READY: "📦 *Pedido Pronto!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} está pronto!",
            self.OrderStatus.SHIPPED: "🚚 *Pedido Enviado!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi enviado!",
            self.OrderStatus.OUT_FOR_DELIVERY: "🛵 *Pedido saiu para entrega!*\n\nOlá {customer_name}! Seu pedido #{order_number} saiu para entrega. Fique de olho! 👀",
            self.OrderStatus.DELIVERED: "📦 *Pedido entregue!*\n\nOlá {customer_name}! Seu pedido #{order_number} foi entregue. Não se esqueça de nos avaliar! Sua opinião é muito importante para nós. 🌟",
            self.OrderStatus.COMPLETED: "✨ *Pedido Finalizado!*\n\nOlá {customer_name}!\n\nObrigado pela sua compra #{order_number}!",
            self.OrderStatus.CANCELLED: "❌ *Pedido Cancelado*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi cancelado.",
            self.OrderStatus.REFUNDED: "💳 *Pedido Reembolsado!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi reembolsado!",
        }

        # Allow store to override the 4 main delivery status messages
        custom_templates = {}
        if self.store and isinstance(self.store.metadata, dict):
            custom_templates = self.store.metadata.get('whatsapp_messages', {})

        status_message_map = {**default_message_map}
        template_key_map = {
            self.OrderStatus.PROCESSING: 'processing',
            self.OrderStatus.CONFIRMED: 'confirmed',
            self.OrderStatus.PAID: 'paid',
            self.OrderStatus.PREPARING: 'preparing',
            self.OrderStatus.READY: 'ready',
            self.OrderStatus.OUT_FOR_DELIVERY: 'out_for_delivery',
            self.OrderStatus.DELIVERED: 'delivered',
            self.OrderStatus.COMPLETED: 'completed',
            self.OrderStatus.CANCELLED: 'cancelled',
        }
        for status_val, tpl_key in template_key_map.items():
            if custom_templates.get(tpl_key, '').strip():
                status_message_map[status_val] = custom_templates[tpl_key].strip()

        message_template = status_message_map.get(new_status)
        if not message_template:
            logger.warning(f"[WhatsAppNotification] RETURN: No template for status: {new_status}")
            return

        notification_key = f'whatsapp_notification_{new_status}'
        if self.metadata.get(notification_key):
            logger.info(f"[WhatsAppNotification] RETURN: Notification already sent - order {self.order_number}, status {new_status}")
            return

        try:
            # Format message
            message_text = message_template.format(
                customer_name=self.customer_name or 'Cliente',
                order_number=self.order_number,
            )
            if new_status == self.OrderStatus.PAID:
                message_text += build_loyalty_status_line(
                    self.store, self.customer if self.customer_id else None)
            logger.info(f"[WhatsAppNotification] ✓ Message template formatted successfully")

            # Normalize phone
            phone = self._normalize_phone_number(self.customer_phone)
            logger.info(f"[WhatsAppNotification] ✓ Phone normalization: {self.customer_phone} → {phone}")
            
            if not phone:
                logger.warning(f"[WhatsAppNotification] RETURN: Invalid phone number {self.customer_phone}")
                return

            # Get WhatsApp account
            from apps.whatsapp.services import MessageService

            account = None
            if self.store:
                logger.info(f"[WhatsAppNotification] → Checking store {self.store.id} for linked account...")
                account = self.store.get_whatsapp_account()
                if account:
                    logger.info(f"[WhatsAppNotification] ✓ Got account from store: {account.id}")
            
            if not account and self.store is None:
                # Default global SÓ para pedido sem loja (legado). Pedido de
                # loja sem conta vinculada NÃO pode sair pelo número de outro
                # tenant (o default aponta pro número de uma loja real).
                logger.info(f"[WhatsAppNotification] → No store, trying default...")
                account = get_default_whatsapp_account(create_if_missing=False)
                if account:
                    logger.info(f"[WhatsAppNotification] ✓ Got default account: {account.id}")

            if not account:
                logger.warning(f"[WhatsAppNotification] RETURN: No WhatsApp account found (store: {self.store}, default: None)")
                return
                
            if not getattr(account, 'phone_number_id', None):
                logger.warning(f"[WhatsAppNotification] RETURN: Account {account.id} missing phone_number_id")
                return

            # Send message
            logger.info(f"[WhatsAppNotification] → Sending message...")
            logger.info(f"  account_id={account.id}, to={phone}, store={self.store.slug if self.store else 'N/A'}")
            
            message_service = MessageService()
            message_service.send_text_message(
                account_id=str(account.id),
                to=phone,
                text=message_text,
                metadata={
                    'source': 'store_order_notification',
                    'order_id': str(self.id),
                    'order_number': self.order_number,
                    'customer_name': self.customer_name or ''
                }
            )
            
            logger.info(f"[WhatsAppNotification] ✓ Message sent successfully!")

            # Update metadata
            self.metadata[notification_key] = timezone.now().isoformat()
            self.save(update_fields=['metadata'])
            logger.info(f"[WhatsAppNotification] ✓ Metadata updated and saved")

        except Exception as e:
            logger.error(f"[WhatsAppNotification] ✗ EXCEPTION: {e}", exc_info=True)
            # Don't re-raise, just log it
            pass

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
