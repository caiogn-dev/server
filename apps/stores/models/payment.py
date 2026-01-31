"""
Store Payment models - Payment management integrated with StoreOrder.

This module provides comprehensive payment management while maintaining
the unified stores architecture. Payments are related to StoreOrder
instead of the legacy Order model.
"""
import uuid
import logging
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

logger = logging.getLogger(__name__)
User = get_user_model()


class StorePaymentGateway(BaseModel):
    """
    Payment gateway configuration for a store.
    Each store can have multiple payment gateways configured.
    """

    class GatewayType(models.TextChoices):
        STRIPE = 'stripe', 'Stripe'
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        PAGSEGURO = 'pagseguro', 'PagSeguro'
        PIX = 'pix', 'PIX'
        CUSTOM = 'custom', 'Custom'

    # Relationship
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='payment_gateways',
        help_text='Store that owns this gateway configuration'
    )

    # Basic info
    name = models.CharField(max_length=255, help_text='Display name for this gateway')
    gateway_type = models.CharField(
        max_length=20,
        choices=GatewayType.choices,
        help_text='Payment gateway provider'
    )

    # Status
    is_enabled = models.BooleanField(default=True, help_text='Whether this gateway is active')
    is_sandbox = models.BooleanField(default=True, help_text='Use sandbox/test mode')
    is_default = models.BooleanField(default=False, help_text='Use as default gateway for this store')

    # Credentials (encrypted at application level if needed)
    api_key = models.CharField(max_length=500, blank=True, help_text='API Key')
    api_secret = models.CharField(max_length=500, blank=True, help_text='API Secret')
    access_token = models.CharField(max_length=500, blank=True, help_text='Access Token (for MP)')
    webhook_secret = models.CharField(max_length=500, blank=True, help_text='Webhook Secret')
    public_key = models.CharField(max_length=500, blank=True, help_text='Public Key (for MP)')

    # URLs
    endpoint_url = models.URLField(blank=True, help_text='Gateway API endpoint')
    webhook_url = models.URLField(blank=True, help_text='Webhook URL for this gateway')

    # Configuration
    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional gateway-specific configuration'
    )

    class Meta:
        db_table = 'store_payment_gateways'
        verbose_name = 'Payment Gateway'
        verbose_name_plural = 'Payment Gateways'
        ordering = ['-is_default', 'name']
        indexes = [
            models.Index(fields=['store', 'is_enabled']),
            models.Index(fields=['store', 'gateway_type']),
            models.Index(fields=['gateway_type', 'is_enabled']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['store', 'gateway_type'],
                name='unique_gateway_type_per_store',
                condition=models.Q(is_enabled=True)
            )
        ]

    def __str__(self):
        return f"{self.store.name} - {self.name} ({self.gateway_type})"

    def save(self, *args, **kwargs):
        # Ensure only one default gateway per store
        if self.is_default:
            StorePaymentGateway.objects.filter(
                store=self.store,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def get_mercadopago_credentials(self):
        """Get Mercado Pago credentials if applicable."""
        if self.gateway_type != self.GatewayType.MERCADOPAGO:
            return None
        return {
            'access_token': self.access_token,
            'public_key': self.public_key,
        }


class StorePayment(BaseModel):
    """
    Payment record for a store order.
    Supports multiple payments per order (installments, retries, partial refunds).
    """

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'
        PARTIALLY_REFUNDED = 'partially_refunded', 'Partially Refunded'

    class PaymentMethod(models.TextChoices):
        CREDIT_CARD = 'credit_card', 'Credit Card'
        DEBIT_CARD = 'debit_card', 'Debit Card'
        PIX = 'pix', 'PIX'
        BOLETO = 'boleto', 'Boleto'
        CASH = 'cash', 'Cash'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        WALLET = 'wallet', 'Digital Wallet'
        OTHER = 'other', 'Other'

    # Relationships
    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.CASCADE,
        related_name='payments',
        help_text='Order this payment belongs to'
    )
    gateway = models.ForeignKey(
        StorePaymentGateway,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        help_text='Payment gateway used'
    )

    # Identifiers
    payment_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text='Internal payment ID (UUID)'
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text='External payment ID (from gateway)'
    )
    external_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text='External reference (order number)'
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        blank=True,
        help_text='Payment method used'
    )

    # Amounts
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Payment amount'
    )
    currency = models.CharField(max_length=3, default='BRL', help_text='Currency code')
    fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Gateway fee'
    )
    net_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Amount after fees'
    )
    refunded_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Total refunded amount'
    )

    # Payer info
    payer_email = models.EmailField(blank=True, help_text='Payer email')
    payer_name = models.CharField(max_length=255, blank=True, help_text='Payer name')
    payer_document = models.CharField(max_length=50, blank=True, help_text='CPF/CNPJ')

    # Payment details (method-specific)
    payment_url = models.URLField(blank=True, help_text='Payment URL for customer')
    qr_code = models.TextField(blank=True, help_text='PIX QR code text')
    qr_code_base64 = models.TextField(blank=True, help_text='PIX QR code base64 image')
    barcode = models.CharField(max_length=255, blank=True, help_text='Boleto barcode')
    ticket_url = models.URLField(blank=True, help_text='Boleto/PDF URL')

    # Timestamps
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Payment expiration')
    paid_at = models.DateTimeField(null=True, blank=True, help_text='When payment was confirmed')
    refunded_at = models.DateTimeField(null=True, blank=True, help_text='When refund was processed')

    # Gateway response and metadata
    gateway_response = models.JSONField(
        default=dict,
        blank=True,
        help_text='Full gateway response'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional metadata'
    )

    # Error info
    error_code = models.CharField(max_length=50, blank=True, help_text='Error code if failed')
    error_message = models.TextField(blank=True, help_text='Error message if failed')

    class Meta:
        db_table = 'store_payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['external_id']),
            models.Index(fields=['gateway', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['payment_method', 'status']),
        ]

    def __str__(self):
        return f"Payment {self.payment_id} - {self.status} - {self.amount}"

    def save(self, *args, **kwargs):
        # Generate payment_id if not set
        if not self.payment_id:
            self.payment_id = str(uuid.uuid4())
        
        # Calculate net amount
        if not self.net_amount and self.amount:
            self.net_amount = self.amount - self.fee
        
        super().save(*args, **kwargs)
        
        # Sync with StoreOrder
        self._sync_with_order()

    def _sync_with_order(self):
        """Sync payment status with StoreOrder."""
        from .order import StoreOrder
        
        order = self.order
        
        # Update StoreOrder payment fields based on this payment
        if self.status == self.PaymentStatus.COMPLETED:
            order.payment_status = StoreOrder.PaymentStatus.PAID
            if not order.paid_at:
                order.paid_at = self.paid_at or self.updated_at
            
            # Update PIX fields if this is a PIX payment
            if self.payment_method == self.PaymentMethod.PIX:
                if self.qr_code and not order.pix_code:
                    order.pix_code = self.qr_code
                if self.qr_code_base64 and not order.pix_qr_code:
                    order.pix_qr_code = self.qr_code_base64
                if self.ticket_url and not order.pix_ticket_url:
                    order.pix_ticket_url = self.ticket_url
            
            # Update payment method and ID
            if not order.payment_method:
                order.payment_method = self.get_payment_method_display()
            if not order.payment_id:
                order.payment_id = self.external_id or self.payment_id
                
        elif self.status == self.PaymentStatus.FAILED:
            # Only update if no other successful payments
            if not order.payments.filter(status=self.PaymentStatus.COMPLETED).exists():
                order.payment_status = StoreOrder.PaymentStatus.FAILED
                
        elif self.status in [self.PaymentStatus.REFUNDED, self.PaymentStatus.PARTIALLY_REFUNDED]:
            # Check total refunded amount
            total_refunded = order.payments.aggregate(
                total=models.Sum('refunded_amount')
            )['total'] or 0
            
            if total_refunded >= order.total:
                order.payment_status = StoreOrder.PaymentStatus.REFUNDED
            else:
                order.payment_status = StoreOrder.PaymentStatus.PARTIALLY_REFUNDED
        
        order.save(update_fields=[
            'payment_status', 'paid_at', 'pix_code', 'pix_qr_code',
            'pix_ticket_url', 'payment_method', 'payment_id', 'updated_at'
        ])

    def can_process(self):
        """Check if payment can be processed."""
        return self.status in [self.PaymentStatus.PENDING, self.PaymentStatus.FAILED]

    def can_confirm(self):
        """Check if payment can be confirmed."""
        return self.status in [self.PaymentStatus.PENDING, self.PaymentStatus.PROCESSING]

    def can_cancel(self):
        """Check if payment can be cancelled."""
        return self.status in [self.PaymentStatus.PENDING, self.PaymentStatus.PROCESSING]

    def can_refund(self):
        """Check if payment can be refunded."""
        return self.status == self.PaymentStatus.COMPLETED and self.refunded_amount < self.amount

    def get_refundable_amount(self):
        """Get remaining amount that can be refunded."""
        return self.amount - self.refunded_amount


class StorePaymentWebhookEvent(BaseModel):
    """
    Log of payment webhook events for auditing and debugging.
    """

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DUPLICATE = 'duplicate', 'Duplicate'
        IGNORED = 'ignored', 'Ignored'

    # Relationships
    gateway = models.ForeignKey(
        StorePaymentGateway,
        on_delete=models.CASCADE,
        related_name='webhook_events',
        help_text='Gateway that received this event'
    )
    payment = models.ForeignKey(
        StorePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events',
        help_text='Related payment (if identified)'
    )
    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_webhook_events',
        help_text='Related order (if identified)'
    )

    # Event info
    event_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='External event ID'
    )
    event_type = models.CharField(max_length=100, help_text='Event type (e.g., payment.created)')

    # Processing status
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )

    # Data
    payload = models.JSONField(help_text='Full webhook payload')
    headers = models.JSONField(default=dict, blank=True, help_text='Request headers')

    # Processing info
    processed_at = models.DateTimeField(null=True, blank=True, help_text='When event was processed')
    retry_count = models.PositiveIntegerField(default=0, help_text='Number of retry attempts')
    error_message = models.TextField(blank=True, help_text='Error message if processing failed')

    class Meta:
        db_table = 'store_payment_webhook_events'
        verbose_name = 'Payment Webhook Event'
        verbose_name_plural = 'Payment Webhook Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['gateway', 'event_type']),
            models.Index(fields=['processing_status', 'created_at']),
            models.Index(fields=['event_id', 'gateway']),
            models.Index(fields=['payment', 'event_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['gateway', 'event_id'],
                name='unique_event_per_gateway'
            )
        ]

    def __str__(self):
        return f"{self.event_type}: {self.event_id} ({self.processing_status})"

    def mark_processed(self):
        """Mark event as successfully processed."""
        self.processing_status = self.ProcessingStatus.COMPLETED
        self.processed_at = models.DateTimeField()._get_val_from_obj(self)
        from django.utils import timezone
        self.processed_at = timezone.now()
        self.save(update_fields=['processing_status', 'processed_at'])

    def mark_failed(self, error_message):
        """Mark event as failed."""
        self.processing_status = self.ProcessingStatus.FAILED
        self.error_message = error_message
        self.retry_count += 1
        self.save(update_fields=['processing_status', 'error_message', 'retry_count'])

    def mark_duplicate(self):
        """Mark event as duplicate."""
        self.processing_status = self.ProcessingStatus.DUPLICATE
        self.save(update_fields=['processing_status'])
