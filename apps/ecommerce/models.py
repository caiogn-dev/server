"""
E-commerce models for Pastita integration.
Products, Cart, CartItem - compatible with existing Orders/Payments system.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Product(models.Model):
    """Product model for e-commerce catalog"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    image_url = models.URLField(blank=True, null=True, help_text="External image URL (S3, etc)")
    category = models.CharField(max_length=100, blank=True, null=True)
    sku = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} - R$ {self.price}"

    def get_image_url(self):
        """Return image URL from field or external URL"""
        if self.image:
            return self.image.url
        return self.image_url or ''


class Cart(models.Model):
    """Shopping cart model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='ecommerce_cart',
        null=True,
        blank=True
    )
    session_key = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'

    def __str__(self):
        if self.user:
            return f"Cart of {self.user.email}"
        return f"Cart {self.id} (anonymous)"

    def get_total(self) -> Decimal:
        """Calculate cart total"""
        return sum(item.get_subtotal() for item in self.items.all())

    def get_item_count(self) -> int:
        """Get total number of items in cart"""
        return sum(item.quantity for item in self.items.all())

    def get_items_data(self) -> list:
        """Get cart items as list of dicts for webhooks"""
        return [
            {
                'id': str(item.product.id),
                'name': item.product.name,
                'quantity': item.quantity,
                'price': float(item.product.price),
                'subtotal': float(item.get_subtotal()),
            }
            for item in self.items.select_related('product').all()
        ]


class CartItem(models.Model):
    """Individual items in a shopping cart"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ['cart', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def get_subtotal(self) -> Decimal:
        """Calculate subtotal for this item"""
        return self.product.price * self.quantity


class Checkout(models.Model):
    """Checkout session for payment processing - integrates with payments app"""
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.SET_NULL, null=True, blank=True)
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='ecommerce_checkout',
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ecommerce_checkouts',
        null=True,
        blank=True
    )
    
    # Payment info
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    session_token = models.CharField(max_length=255, unique=True)
    
    # Mercado Pago
    mercado_pago_preference_id = models.CharField(max_length=255, blank=True, null=True)
    mercado_pago_payment_id = models.CharField(max_length=255, blank=True, null=True)
    payment_link = models.URLField(blank=True, null=True)
    pix_code = models.TextField(blank=True, null=True)
    pix_qr_code = models.TextField(blank=True, null=True)
    
    # Customer info
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    
    # Shipping address
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=50, blank=True)
    shipping_zip_code = models.CharField(max_length=20, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Checkout'
        verbose_name_plural = 'Checkouts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_status']),
            models.Index(fields=['session_token']),
            models.Index(fields=['mercado_pago_payment_id']),
            models.Index(fields=['customer_phone']),
        ]

    def __str__(self):
        return f"Checkout {self.session_token[:8]}... - {self.payment_status}"

    def mark_completed(self):
        """Mark checkout as completed"""
        self.payment_status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['payment_status', 'completed_at', 'updated_at'])
