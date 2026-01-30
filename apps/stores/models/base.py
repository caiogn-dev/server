"""
Base store models - Store, StoreIntegration, StoreWebhook.
"""
import uuid
import logging
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel
from apps.core.utils import token_encryption, mask_token, build_absolute_media_url

logger = logging.getLogger(__name__)
User = get_user_model()


class Store(BaseModel):
    """
    Central store entity that owns all products, orders, and integrations.
    Each store can have its own WhatsApp, Instagram, Twitter, etc.
    """

    class StoreType(models.TextChoices):
        FOOD = 'food', 'Food & Restaurant'
        RETAIL = 'retail', 'Retail'
        SERVICES = 'services', 'Services'
        DIGITAL = 'digital', 'Digital Products'
        OTHER = 'other', 'Other'

    class StoreStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'
        PENDING = 'pending', 'Pending Setup'

    # Basic Info
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    store_type = models.CharField(
        max_length=20,
        choices=StoreType.choices,
        default=StoreType.OTHER
    )
    status = models.CharField(
        max_length=20,
        choices=StoreStatus.choices,
        default=StoreStatus.PENDING
    )

    # Branding
    logo = models.ImageField(upload_to='stores/logos/', blank=True, null=True)
    logo_url = models.URLField(blank=True, help_text="External logo URL")
    banner = models.ImageField(upload_to='stores/banners/', blank=True, null=True)
    banner_url = models.URLField(blank=True, help_text="External banner URL")
    primary_color = models.CharField(max_length=7, default='#000000', help_text="Hex color code")
    secondary_color = models.CharField(max_length=7, default='#ffffff', help_text="Hex color code")

    # Contact Info
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True, help_text="WhatsApp number for customer contact")

    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, default='BR')
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # Business Settings
    currency = models.CharField(max_length=3, default='BRL')
    timezone = models.CharField(max_length=50, default='America/Sao_Paulo')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Delivery Settings
    delivery_enabled = models.BooleanField(default=True)
    pickup_enabled = models.BooleanField(default=True)
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_delivery_threshold = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    default_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('10.00'))

    # Operating Hours (JSON: {"monday": {"open": "09:00", "close": "18:00"}, ...})
    operating_hours = models.JSONField(default=dict, blank=True)

    # Owner
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_stores'
    )

    # Staff (users who can manage this store)
    staff = models.ManyToManyField(
        User,
        related_name='managed_stores',
        blank=True
    )

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'stores'
        verbose_name = 'Store'
        verbose_name_plural = 'Stores'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_logo_url(self):
        if self.logo:
            return build_absolute_media_url(self.logo.url)
        return build_absolute_media_url(self.logo_url or '')

    def get_banner_url(self):
        if self.banner:
            return build_absolute_media_url(self.banner.url)
        return build_absolute_media_url(self.banner_url or '')

    def is_open(self):
        """Check if store is currently open based on operating hours."""
        if not self.operating_hours:
            return True

        now = timezone.now()
        day_name = now.strftime('%A').lower()
        hours = self.operating_hours.get(day_name)

        if not hours:
            return False

        current_time = now.strftime('%H:%M')
        return hours.get('open', '00:00') <= current_time <= hours.get('close', '23:59')


class StoreIntegration(BaseModel):
    """
    Social network and platform integrations for a store.
    Supports WhatsApp, Instagram, Twitter, Facebook, etc.
    """

    class IntegrationType(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp Business'
        INSTAGRAM = 'instagram', 'Instagram'
        FACEBOOK = 'facebook', 'Facebook'
        TWITTER = 'twitter', 'Twitter/X'
        TELEGRAM = 'telegram', 'Telegram'
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        STRIPE = 'stripe', 'Stripe'
        EMAIL = 'email', 'Email (SMTP)'
        WEBHOOK = 'webhook', 'Custom Webhook'

    class IntegrationStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        ERROR = 'error', 'Error'
        PENDING = 'pending', 'Pending Setup'

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='integrations'
    )

    integration_type = models.CharField(
        max_length=20,
        choices=IntegrationType.choices
    )
    name = models.CharField(max_length=255, help_text="Display name for this integration")
    status = models.CharField(
        max_length=20,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.PENDING
    )

    # Credentials (encrypted)
    api_key_encrypted = models.TextField(blank=True)
    api_secret_encrypted = models.TextField(blank=True)
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)

    # Platform-specific IDs
    external_id = models.CharField(max_length=255, blank=True, help_text="Platform-specific ID")
    phone_number_id = models.CharField(max_length=100, blank=True, help_text="WhatsApp Phone Number ID")
    waba_id = models.CharField(max_length=100, blank=True, help_text="WhatsApp Business Account ID")

    # Webhook configuration
    webhook_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)
    webhook_verify_token = models.CharField(max_length=255, blank=True)

    # Settings
    settings = models.JSONField(default=dict, blank=True, help_text="Platform-specific settings")

    # Token expiration
    token_expires_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    last_error = models.TextField(blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'store_integrations'
        verbose_name = 'Store Integration'
        verbose_name_plural = 'Store Integrations'
        unique_together = ['store', 'integration_type', 'external_id']
        ordering = ['store', 'integration_type']

    def __str__(self):
        return f"{self.store.name} - {self.get_integration_type_display()}"

    # Encrypted field properties
    @property
    def api_key(self) -> str:
        if not self.api_key_encrypted:
            return ''
        return token_encryption.decrypt(self.api_key_encrypted)

    @api_key.setter
    def api_key(self, value: str):
        self.api_key_encrypted = token_encryption.encrypt(value) if value else ''

    @property
    def api_secret(self) -> str:
        if not self.api_secret_encrypted:
            return ''
        return token_encryption.decrypt(self.api_secret_encrypted)

    @api_secret.setter
    def api_secret(self, value: str):
        self.api_secret_encrypted = token_encryption.encrypt(value) if value else ''

    @property
    def access_token(self) -> str:
        if not self.access_token_encrypted:
            return ''
        return token_encryption.decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value: str):
        self.access_token_encrypted = token_encryption.encrypt(value) if value else ''

    @property
    def refresh_token(self) -> str:
        if not self.refresh_token_encrypted:
            return ''
        return token_encryption.decrypt(self.refresh_token_encrypted)

    @refresh_token.setter
    def refresh_token(self, value: str):
        self.refresh_token_encrypted = token_encryption.encrypt(value) if value else ''

    @property
    def masked_api_key(self) -> str:
        return mask_token(self.api_key) if self.api_key else ''

    @property
    def masked_access_token(self) -> str:
        return mask_token(self.access_token) if self.access_token else ''

    def set_error(self, error_message: str):
        """Record an error for this integration."""
        self.last_error = error_message
        self.last_error_at = timezone.now()
        self.status = self.IntegrationStatus.ERROR
        self.save(update_fields=['last_error', 'last_error_at', 'status', 'updated_at'])

    def clear_error(self):
        """Clear error state."""
        self.last_error = ''
        self.last_error_at = None
        self.status = self.IntegrationStatus.ACTIVE
        self.save(update_fields=['last_error', 'last_error_at', 'status', 'updated_at'])


class StoreWebhook(BaseModel):
    """
    Webhook configurations for store events.
    Allows stores to receive notifications for orders, payments, etc.
    """

    class WebhookEvent(models.TextChoices):
        ORDER_CREATED = 'order.created', 'Order Created'
        ORDER_UPDATED = 'order.updated', 'Order Updated'
        ORDER_PAID = 'order.paid', 'Order Paid'
        ORDER_SHIPPED = 'order.shipped', 'Order Shipped'
        ORDER_DELIVERED = 'order.delivered', 'Order Delivered'
        ORDER_CANCELLED = 'order.cancelled', 'Order Cancelled'
        PAYMENT_RECEIVED = 'payment.received', 'Payment Received'
        PAYMENT_FAILED = 'payment.failed', 'Payment Failed'
        PAYMENT_REFUNDED = 'payment.refunded', 'Payment Refunded'
        CUSTOMER_CREATED = 'customer.created', 'Customer Created'
        PRODUCT_LOW_STOCK = 'product.low_stock', 'Product Low Stock'
        MESSAGE_RECEIVED = 'message.received', 'Message Received'

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='webhooks'
    )

    name = models.CharField(max_length=255)
    url = models.URLField()
    secret = models.CharField(max_length=255, blank=True, help_text="Secret for signature verification")
    events = models.JSONField(default=list, help_text="List of events to trigger this webhook")

    # Headers to include in webhook requests
    headers = models.JSONField(default=dict, blank=True)

    # Retry configuration
    max_retries = models.PositiveIntegerField(default=3)
    retry_delay = models.PositiveIntegerField(default=60, help_text="Delay in seconds between retries")

    # Stats
    total_calls = models.PositiveIntegerField(default=0)
    successful_calls = models.PositiveIntegerField(default=0)
    failed_calls = models.PositiveIntegerField(default=0)
    last_called_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = 'store_webhooks'
        verbose_name = 'Store Webhook'
        verbose_name_plural = 'Store Webhooks'
        ordering = ['store', 'name']

    def __str__(self):
        return f"{self.store.name} - {self.name}"

    def record_call(self, success: bool, error: str = ''):
        """Record a webhook call result."""
        self.total_calls += 1
        self.last_called_at = timezone.now()

        if success:
            self.successful_calls += 1
            self.last_success_at = timezone.now()
        else:
            self.failed_calls += 1
            self.last_failure_at = timezone.now()
            self.last_error = error

        self.save(update_fields=[
            'total_calls', 'successful_calls', 'failed_calls',
            'last_called_at', 'last_success_at', 'last_failure_at',
            'last_error', 'updated_at'
        ])
