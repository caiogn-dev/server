"""
Payments models - Payment management.
"""
from django.db import models
from apps.core.models import BaseModel


class PaymentGateway(BaseModel):
    """Payment gateway configuration."""
    
    class GatewayType(models.TextChoices):
        STRIPE = 'stripe', 'Stripe'
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        PAGSEGURO = 'pagseguro', 'PagSeguro'
        PIX = 'pix', 'PIX'
        CUSTOM = 'custom', 'Custom'

    name = models.CharField(max_length=255)
    gateway_type = models.CharField(max_length=20, choices=GatewayType.choices)
    
    is_enabled = models.BooleanField(default=True)
    is_sandbox = models.BooleanField(default=True)
    
    api_key_encrypted = models.TextField(blank=True)
    api_secret_encrypted = models.TextField(blank=True)
    webhook_secret_encrypted = models.TextField(blank=True)
    
    endpoint_url = models.URLField(blank=True)
    webhook_url = models.URLField(blank=True)
    
    configuration = models.JSONField(default=dict, blank=True)
    
    accounts = models.ManyToManyField(
        'whatsapp.WhatsAppAccount',
        related_name='payment_gateways',
        blank=True
    )

    class Meta:
        db_table = 'payment_gateways'
        verbose_name = 'Payment Gateway'
        verbose_name_plural = 'Payment Gateways'

    def __str__(self):
        return f"{self.name} ({self.gateway_type})"


class Payment(BaseModel):
    """Payment model."""
    
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
        CASH = 'cash', 'Dinheiro'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        WALLET = 'wallet', 'Digital Wallet'
        OTHER = 'other', 'Other'

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='payments'
    )
    gateway = models.ForeignKey(
        PaymentGateway,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )
    
    payment_id = models.CharField(max_length=100, unique=True, db_index=True)
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        blank=True
    )
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='BRL')
    
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    payer_email = models.EmailField(blank=True)
    payer_name = models.CharField(max_length=255, blank=True)
    payer_document = models.CharField(max_length=50, blank=True)
    
    payment_url = models.URLField(blank=True)
    qr_code = models.TextField(blank=True)
    qr_code_base64 = models.TextField(blank=True)
    barcode = models.CharField(max_length=255, blank=True)
    
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    gateway_response = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['external_id']),
        ]

    def __str__(self):
        return f"Payment {self.payment_id} - {self.status}"


class PaymentWebhookEvent(BaseModel):
    """Payment webhook event log."""
    
    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DUPLICATE = 'duplicate', 'Duplicate'

    gateway = models.ForeignKey(
        PaymentGateway,
        on_delete=models.CASCADE,
        related_name='webhook_events'
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )
    
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )
    
    payload = models.JSONField()
    headers = models.JSONField(default=dict)
    
    processed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'payment_webhook_events'
        verbose_name = 'Payment Webhook Event'
        verbose_name_plural = 'Payment Webhook Events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type}: {self.event_id}"
