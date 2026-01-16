"""
Store models - Multi-store management with social integrations.
Central entity that links products, orders, payments, and social networks.

This is the UNIFIED e-commerce system that supports:
- Multiple stores (Pastita is just one store)
- Generic products with optional specialized types (sauce, meat, pasta)
- Combos/bundles
- Carts with products and combos
- Orders with full payment integration
- Coupons and delivery zones per store
- Wishlist functionality
"""
import uuid
import logging
import os
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.templatetags.static import static
from apps.core.models import BaseModel
from apps.core.utils import token_encryption, mask_token

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
            return self.logo.url
        return self.logo_url or ''
    
    def get_banner_url(self):
        if self.banner:
            return self.banner.url
        return self.banner_url or ''
    
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


class StoreCategory(models.Model):
    """Product categories specific to a store."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='categories'
    )
    
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='stores/categories/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_categories'
        verbose_name = 'Store Category'
        verbose_name_plural = 'Store Categories'
        unique_together = ['store', 'slug']
        ordering = ['store', 'sort_order', 'name']
    
    def __str__(self):
        return f"{self.store.name} - {self.name}"
    
    def get_image_url(self):
        if self.image:
            return self.image.url
        return self.image_url or ''


class StoreProduct(BaseModel):
    """
    Generic product model for any store type.
    Supports variants, stock management, dynamic product types, and rich metadata.
    
    Products can be linked to a StoreProductType which defines custom fields.
    The type_attributes JSONField stores values for those custom fields.
    """
    
    class ProductStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        OUT_OF_STOCK = 'out_of_stock', 'Out of Stock'
        DISCONTINUED = 'discontinued', 'Discontinued'
    
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='products'
    )
    category = models.ForeignKey(
        StoreCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    # Dynamic product type (e.g., Molho, Carne, Rondelli for Pastita)
    product_type = models.ForeignKey(
        'StoreProductType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        help_text="Product type defines custom fields for this product"
    )
    # Values for custom fields defined by product_type
    type_attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Values for custom fields defined by the product type"
    )
    
    # Basic Info
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    
    # SKU and Barcode
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    barcode = models.CharField(max_length=100, blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Stock
    track_stock = models.BooleanField(default=True)
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    allow_backorder = models.BooleanField(default=False)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.ACTIVE
    )
    featured = models.BooleanField(default=False)
    
    # Images
    main_image = models.ImageField(upload_to='stores/products/', blank=True, null=True)
    main_image_url = models.URLField(blank=True)
    images = models.JSONField(default=list, blank=True, help_text="List of additional image URLs")
    
    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    
    # Physical properties (for shipping)
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    weight_unit = models.CharField(max_length=10, default='kg')
    dimensions = models.JSONField(default=dict, blank=True, help_text="{'length': 0, 'width': 0, 'height': 0}")
    
    # Attributes (flexible key-value pairs)
    attributes = models.JSONField(default=dict, blank=True)
    
    # Tags
    tags = models.JSONField(default=list, blank=True)
    
    # Sort order
    sort_order = models.PositiveIntegerField(default=0)
    
    # Stats
    view_count = models.PositiveIntegerField(default=0)
    sold_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'store_products'
        verbose_name = 'Store Product'
        verbose_name_plural = 'Store Products'
        unique_together = ['store', 'slug']
        ordering = ['store', 'sort_order', '-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['store', 'category']),
            models.Index(fields=['store', 'sku']),
        ]
    
    def __str__(self):
        return f"{self.store.name} - {self.name}"
    
    def get_main_image_url(self):
        if self.main_image:
            return self.main_image.url
        return self.main_image_url or ''
    
    @property
    def is_on_sale(self):
        return self.compare_at_price and self.compare_at_price > self.price
    
    @property
    def discount_percentage(self):
        if self.is_on_sale:
            return int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0
    
    @property
    def is_low_stock(self):
        return self.track_stock and self.stock_quantity <= self.low_stock_threshold
    
    @property
    def is_in_stock(self):
        if not self.track_stock:
            return True
        return self.stock_quantity > 0 or self.allow_backorder
    
    def decrement_stock(self, quantity: int = 1):
        """Safely decrement stock quantity."""
        if self.track_stock:
            from django.db.models import F
            StoreProduct.objects.filter(id=self.id).update(
                stock_quantity=F('stock_quantity') - quantity,
                sold_count=F('sold_count') + quantity
            )
            self.refresh_from_db()


class StoreProductVariant(models.Model):
    """Product variants (size, color, etc.)"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        StoreProduct,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    
    # Pricing (overrides product price if set)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Stock
    stock_quantity = models.IntegerField(default=0)
    
    # Options (e.g., {"size": "M", "color": "Red"})
    options = models.JSONField(default=dict)
    
    # Image
    image = models.ImageField(upload_to='stores/variants/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_product_variants'
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        ordering = ['product', 'sort_order']
    
    def __str__(self):
        return f"{self.product.name} - {self.name}"
    
    def get_price(self):
        return self.price if self.price is not None else self.product.price
    
    def get_image_url(self):
        if self.image:
            return self.image.url
        if self.image_url:
            return self.image_url
        return self.product.get_main_image_url()


# =============================================================================
# WISHLIST MODEL
# =============================================================================

class StoreWishlist(models.Model):
    """User's wishlist for a specific store."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='wishlists'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_wishlists'
    )
    products = models.ManyToManyField(
        StoreProduct,
        related_name='wishlisted_by',
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_wishlists'
        verbose_name = 'Wishlist'
        verbose_name_plural = 'Wishlists'
        unique_together = ['store', 'user']
    
    def __str__(self):
        return f"{self.user.email}'s wishlist for {self.store.name}"


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
    
    # Order number (human-readable)
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Security token for public access (payment page, order tracking)
    # This token is required to view order details without authentication
    access_token = models.CharField(
        max_length=64, 
        unique=True, 
        db_index=True,
        default='',
        blank=True,
        help_text='Secure token for public order access (payment page, tracking)'
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
    pix_ticket_url = models.URLField(max_length=500, blank=True, help_text='Link to Mercado Pago payment page with QR code')
    
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
        """Generate a secure random access token for public order access."""
        import secrets
        return secrets.token_urlsafe(32)  # 43 characters, cryptographically secure
    
    def update_status(self, new_status: str, notify: bool = True):
        """Update order status and optionally send notifications."""
        old_status = self.status
        self.status = new_status
        
        # Update timestamps
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
        
        # Send webhook notification
        if notify:
            self.send_status_webhook(old_status, new_status)
        
        # Trigger email automation for status changes
        self._trigger_status_email_automation(new_status)
        
        return self
    
    def _trigger_status_email_automation(self, new_status: str):
        """Trigger email automation based on status change."""
        try:
            from apps.stores.services.checkout_service import trigger_order_email_automation
            
            status_trigger_map = {
                self.OrderStatus.CONFIRMED: 'order_confirmed',
                self.OrderStatus.PAID: 'payment_confirmed',
                self.OrderStatus.SHIPPED: 'order_shipped',
                self.OrderStatus.OUT_FOR_DELIVERY: 'order_shipped',  # Same email as shipped
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
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to trigger email automation for order {self.order_number}: {e}")
    
    def send_status_webhook(self, old_status: str, new_status: str):
        """Send webhook notification for status change."""
        from .services import webhook_service
        
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
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'total': str(self.total),
        })


class StoreOrderItem(models.Model):
    """Individual items in an order."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        StoreOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    # Product reference (may be null if product deleted)
    product = models.ForeignKey(
        StoreProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    variant = models.ForeignKey(
        StoreProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Denormalized product info (preserved even if product deleted)
    product_name = models.CharField(max_length=255)
    variant_name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=100, blank=True)
    
    # Pricing
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Options/customizations
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


class StoreCustomer(BaseModel):
    """
    Customer profile specific to a store.
    Links to User but stores store-specific data.
    """
    
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='customers'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_profiles'
    )
    
    # Contact info (may differ from User)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    
    # Social links
    instagram = models.CharField(max_length=100, blank=True)
    twitter = models.CharField(max_length=100, blank=True)
    facebook = models.CharField(max_length=100, blank=True)
    
    # Addresses
    addresses = models.JSONField(default=list, blank=True)
    default_address_index = models.PositiveIntegerField(default=0)
    
    # Stats
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_order_at = models.DateTimeField(null=True, blank=True)
    
    # Tags and notes
    tags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    
    # Marketing
    accepts_marketing = models.BooleanField(default=False)
    marketing_opt_in_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'store_customers'
        verbose_name = 'Store Customer'
        verbose_name_plural = 'Store Customers'
        unique_together = ['store', 'user']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.store.name} - {self.user.email}"
    
    def get_default_address(self):
        if self.addresses and len(self.addresses) > self.default_address_index:
            return self.addresses[self.default_address_index]
        return None
    
    def update_stats(self):
        """Update customer statistics from orders."""
        from django.db.models import Sum, Count
        
        stats = StoreOrder.objects.filter(
            store=self.store,
            customer=self.user,
            status__in=['paid', 'completed', 'delivered']
        ).aggregate(
            total_orders=Count('id'),
            total_spent=Sum('total')
        )
        
        self.total_orders = stats['total_orders'] or 0
        self.total_spent = stats['total_spent'] or Decimal('0.00')
        
        last_order = StoreOrder.objects.filter(
            store=self.store,
            customer=self.user
        ).order_by('-created_at').first()
        
        if last_order:
            self.last_order_at = last_order.created_at
        
        self.save(update_fields=['total_orders', 'total_spent', 'last_order_at', 'updated_at'])


# =============================================================================
# CART MODELS
# =============================================================================

class StoreCart(models.Model):
    """
    Shopping cart for a store.
    Can be linked to a user or be anonymous (session-based).
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='carts'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_carts',
        null=True,
        blank=True
    )
    # Session ID for anonymous carts
    session_key = models.CharField(max_length=255, blank=True, db_index=True)
    
    # Cart status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Metadata (for custom data)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'store_carts'
        verbose_name = 'Store Cart'
        verbose_name_plural = 'Store Carts'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['store', 'user']),
            models.Index(fields=['store', 'session_key']),
        ]
    
    def __str__(self):
        if self.user:
            return f"Cart for {self.user.email} at {self.store.name}"
        return f"Anonymous cart at {self.store.name}"
    
    @property
    def subtotal(self):
        """Calculate cart subtotal."""
        return sum(item.subtotal for item in self.items.all())
    
    @property
    def item_count(self):
        """Total number of items in cart."""
        return sum(item.quantity for item in self.items.all())
    
    @property
    def is_empty(self):
        return self.items.count() == 0
    
    def clear(self):
        """Remove all items from cart."""
        self.items.all().delete()
    
    def merge_with(self, other_cart):
        """Merge another cart into this one (used when user logs in)."""
        for item in other_cart.items.all():
            existing = self.items.filter(
                product=item.product,
                variant=item.variant
            ).first()
            
            if existing:
                existing.quantity += item.quantity
                existing.save()
            else:
                item.cart = self
                item.save()
        
        other_cart.delete()
    
    @classmethod
    def get_or_create_for_user(cls, store, user):
        """Get or create an active cart for a user."""
        cart, created = cls.objects.get_or_create(
            store=store,
            user=user,
            is_active=True,
            defaults={'metadata': {}}
        )
        return cart
    
    @classmethod
    def get_or_create_for_session(cls, store, session_key):
        """Get or create an active cart for a session."""
        cart, created = cls.objects.get_or_create(
            store=store,
            session_key=session_key,
            user__isnull=True,
            is_active=True,
            defaults={'metadata': {}}
        )
        return cart


class StoreCartItem(models.Model):
    """Individual item in a shopping cart."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(
        StoreCart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        StoreProduct,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    variant = models.ForeignKey(
        StoreProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cart_items'
    )
    
    quantity = models.PositiveIntegerField(default=1)
    
    # Custom options/notes for this item
    options = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_cart_items'
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ['cart', 'product', 'variant']
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name}"
    
    @property
    def unit_price(self):
        """Get the unit price (from variant or product)."""
        if self.variant and self.variant.price:
            return self.variant.price
        return self.product.price
    
    @property
    def subtotal(self):
        """Calculate item subtotal."""
        return self.unit_price * self.quantity
    
    def save(self, *args, **kwargs):
        # Update cart timestamp
        super().save(*args, **kwargs)
        StoreCart.objects.filter(id=self.cart_id).update(updated_at=timezone.now())


# =============================================================================
# PRODUCT TYPE DEFINITIONS (for dynamic product types like Pastita)
# =============================================================================

class StoreProductType(models.Model):
    """
    Dynamic product type definitions for a store.
    Allows stores to define custom product types (like Molho, Carne, Rondelli).
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='product_types'
    )
    
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    
    # Icon/image for this type
    icon = models.CharField(max_length=50, blank=True, help_text="Icon name or emoji")
    image = models.ImageField(upload_to='stores/product_types/', blank=True, null=True)
    
    # Field definitions for this product type
    # Example: [{"name": "tipo", "type": "select", "options": ["4queijos", "sugo"], "required": true}]
    custom_fields = models.JSONField(
        default=list,
        blank=True,
        help_text="Custom field definitions for products of this type"
    )
    
    # Display settings
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    show_in_menu = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_product_types'
        verbose_name = 'Product Type'
        verbose_name_plural = 'Product Types'
        unique_together = ['store', 'slug']
        ordering = ['store', 'sort_order', 'name']
    
    def __str__(self):
        return f"{self.store.name} - {self.name}"


class StoreCombo(models.Model):
    """
    Combo/bundle of products for a store.
    Allows creating product bundles with special pricing.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='combos'
    )
    
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Original price before discount"
    )
    
    # Image
    image = models.ImageField(upload_to='stores/combos/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    
    # Stock
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_combos'
        verbose_name = 'Store Combo'
        verbose_name_plural = 'Store Combos'
        unique_together = ['store', 'slug']
        ordering = ['store', '-created_at']
    
    def __str__(self):
        return f"{self.store.name} - {self.name}"
    
    def get_image_url(self):
        if self.image:
            return self.image.url
        return self.image_url or ''
    
    @property
    def savings(self):
        """Calculate savings compared to buying items separately."""
        if self.compare_at_price:
            return self.compare_at_price - self.price
        return Decimal('0.00')
    
    @property
    def savings_percentage(self):
        if self.compare_at_price and self.compare_at_price > 0:
            return int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0


class StoreComboItem(models.Model):
    """Individual item in a combo."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    combo = models.ForeignKey(
        StoreCombo,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        StoreProduct,
        on_delete=models.CASCADE,
        related_name='combo_items'
    )
    variant = models.ForeignKey(
        StoreProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    quantity = models.PositiveIntegerField(default=1)
    
    # Whether customer can choose options for this item
    allow_customization = models.BooleanField(default=False)
    customization_options = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'store_combo_items'
        verbose_name = 'Combo Item'
        verbose_name_plural = 'Combo Items'
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name} in {self.combo.name}"


class StoreCartComboItem(models.Model):
    """Combo item in a shopping cart."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(
        StoreCart,
        on_delete=models.CASCADE,
        related_name='combo_items'
    )
    combo = models.ForeignKey(
        StoreCombo,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    
    quantity = models.PositiveIntegerField(default=1)
    
    # Customizations for combo items
    customizations = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_cart_combo_items'
        verbose_name = 'Cart Combo Item'
        verbose_name_plural = 'Cart Combo Items'
    
    def __str__(self):
        return f"{self.quantity}x {self.combo.name}"
    
    @property
    def subtotal(self):
        return self.combo.price * self.quantity


# =============================================================================
# COUPON MODEL (Unified from ecommerce)
# =============================================================================

class StoreCoupon(models.Model):
    """
    Discount coupons for a store.
    Supports percentage and fixed discounts with usage limits.
    """
    
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed Amount'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='coupons'
    )
    
    code = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)
    
    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Constraints
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Usage limits
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    
    # Validity
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    
    # Restrictions
    first_order_only = models.BooleanField(default=False)
    applicable_categories = models.JSONField(default=list, blank=True, help_text="List of category IDs")
    applicable_products = models.JSONField(default=list, blank=True, help_text="List of product IDs")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_coupons'
        verbose_name = 'Store Coupon'
        verbose_name_plural = 'Store Coupons'
        unique_together = ['store', 'code']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.store.name} - {self.code}"
    
    def is_valid(self, subtotal=None, user=None):
        """Check if coupon is valid for use."""
        now = timezone.now()
        
        if not self.is_active:
            return False, "Cupom inativo"
        
        if now < self.valid_from:
            return False, "Cupom ainda não está válido"
        
        if now > self.valid_until:
            return False, "Cupom expirado"
        
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "Limite de uso atingido"
        
        if subtotal and subtotal < self.min_purchase:
            return False, f"Valor mínimo de R$ {self.min_purchase:.2f}"
        
        if self.first_order_only and user:
            has_orders = StoreOrder.objects.filter(
                store=self.store,
                customer=user,
                status__in=['paid', 'completed', 'delivered']
            ).exists()
            if has_orders:
                return False, "Cupom válido apenas para primeira compra"
        
        return True, None
    
    def calculate_discount(self, subtotal):
        """Calculate discount amount for a given subtotal."""
        valid, _ = self.is_valid(subtotal)
        if not valid:
            return Decimal('0.00')
        
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = subtotal * (self.discount_value / 100)
        else:
            discount = self.discount_value
        
        if self.max_discount:
            discount = min(discount, self.max_discount)
        
        return min(discount, subtotal)
    
    def increment_usage(self) -> bool:
        """Atomically increment usage count with race condition protection."""
        from django.db.models import F
        
        if self.usage_limit:
            updated = StoreCoupon.objects.filter(
                id=self.id,
                used_count__lt=self.usage_limit
            ).update(
                used_count=F('used_count') + 1,
                updated_at=timezone.now()
            )
            return updated > 0
        else:
            StoreCoupon.objects.filter(id=self.id).update(
                used_count=F('used_count') + 1,
                updated_at=timezone.now()
            )
            return True


# =============================================================================
# DELIVERY ZONE MODEL (Unified from ecommerce)
# =============================================================================

class StoreDeliveryZone(models.Model):
    """
    Delivery zones for a store with flexible zone definitions.
    Supports distance bands, custom ranges, ZIP codes, polygons, and time-based zones.
    """
    
    class ZoneType(models.TextChoices):
        DISTANCE_BAND = 'distance_band', 'Distance Band'
        CUSTOM_DISTANCE = 'custom_distance', 'Custom Distance Range'
        ZIP_RANGE = 'zip_range', 'ZIP Code Range'
        POLYGON = 'polygon', 'Custom Polygon'
        TIME_BASED = 'time_based', 'Time-based (Isochrone)'
    
    DISTANCE_BAND_CHOICES = [
        ('0_2', '0-2 km'),
        ('2_5', '2-5 km'),
        ('5_8', '5-8 km'),
        ('8_12', '8-12 km'),
        ('12_15', '12-15 km'),
        ('15_20', '15-20 km'),
        ('20_30', '20-30 km'),
        ('30_plus', '30+ km'),
    ]
    
    DISTANCE_BAND_RANGES = {
        '0_2': (Decimal('0.00'), Decimal('2.00')),
        '2_5': (Decimal('2.00'), Decimal('5.00')),
        '5_8': (Decimal('5.00'), Decimal('8.00')),
        '8_12': (Decimal('8.00'), Decimal('12.00')),
        '12_15': (Decimal('12.00'), Decimal('15.00')),
        '15_20': (Decimal('15.00'), Decimal('20.00')),
        '20_30': (Decimal('20.00'), Decimal('30.00')),
        '30_plus': (Decimal('30.00'), Decimal('999.00')),
    }
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='delivery_zones'
    )
    
    name = models.CharField(max_length=100)
    zone_type = models.CharField(
        max_length=20,
        choices=ZoneType.choices,
        default=ZoneType.DISTANCE_BAND
    )
    
    # Distance-based zones
    distance_band = models.CharField(max_length=10, choices=DISTANCE_BAND_CHOICES, blank=True, null=True)
    min_km = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    max_km = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    
    # ZIP code zones
    zip_code_start = models.CharField(max_length=8, blank=True, null=True)
    zip_code_end = models.CharField(max_length=8, blank=True, null=True)
    
    # Time-based zones (isochrone)
    min_minutes = models.PositiveIntegerField(blank=True, null=True)
    max_minutes = models.PositiveIntegerField(blank=True, null=True)
    
    # Polygon zones (GeoJSON format)
    polygon_coordinates = models.JSONField(
        default=list,
        blank=True,
        help_text="GeoJSON coordinates [[lng, lat], ...]"
    )
    
    # Pricing
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    min_fee = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fee_per_km = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    
    # Delivery time
    estimated_minutes = models.PositiveIntegerField(default=30)
    estimated_days = models.PositiveIntegerField(default=0)
    
    # Display
    color = models.CharField(max_length=7, default='#722F37', help_text="Hex color for map")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'store_delivery_zones'
        verbose_name = 'Delivery Zone'
        verbose_name_plural = 'Delivery Zones'
        ordering = ['store', 'sort_order', 'distance_band', 'min_km']
    
    def __str__(self):
        return f"{self.store.name} - {self.name}"
    
    def get_distance_range(self):
        """Get min/max distance for this zone."""
        if self.distance_band:
            return self.DISTANCE_BAND_RANGES.get(self.distance_band, (None, None))
        return (self.min_km, self.max_km)
    
    def matches_distance(self, distance_km):
        """Check if a distance falls within this zone."""
        min_km, max_km = self.get_distance_range()
        if min_km is None or max_km is None:
            return False
        return min_km <= Decimal(str(distance_km)) < max_km
    
    def matches_zip_code(self, zip_code):
        """Check if a ZIP code falls within this zone."""
        if not self.zip_code_start or not self.zip_code_end:
            return False
        clean_zip = zip_code.replace('-', '').replace('.', '')
        return self.zip_code_start <= clean_zip <= self.zip_code_end
    
    def calculate_fee(self, distance_km=None):
        """Calculate delivery fee, optionally based on distance."""
        fee = self.delivery_fee
        
        if self.fee_per_km and distance_km:
            fee += self.fee_per_km * Decimal(str(distance_km))
        
        if self.min_fee:
            fee = max(fee, self.min_fee)
        
        return fee


# =============================================================================
# ORDER ITEM FOR COMBOS
# =============================================================================

class StoreOrderComboItem(models.Model):
    """Combo item in an order (separate from regular items)."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        StoreOrder,
        on_delete=models.CASCADE,
        related_name='combo_items'
    )
    
    combo = models.ForeignKey(
        StoreCombo,
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
