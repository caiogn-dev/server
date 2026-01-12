"""
E-commerce models for Pastita integration.

⚠️ DEPRECATED: This app is deprecated. Use apps.stores instead.

Most models in this file are legacy and should not be used for new code.
Use the unified stores system instead.

Use these models instead:
- Product → stores.StoreProduct
- Cart/CartItem → stores.StoreCart/StoreCartItem
- Wishlist → stores.StoreWishlist
- Coupon → stores.StoreCoupon
- DeliveryZone → stores.StoreDeliveryZone

Note: Coupon and DeliveryZone have `legacy_coupons` and `legacy_delivery_zones`
related_names to avoid conflicts with stores.StoreCoupon and stores.StoreDeliveryZone.

This file is kept for backward compatibility with existing data.
"""
import uuid
import warnings
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# Emit deprecation warning when this module is imported
warnings.warn(
    "apps.ecommerce is deprecated. Use apps.stores instead.",
    DeprecationWarning,
    stacklevel=2
)


def get_store_model():
    """Lazy import to avoid circular imports."""
    from apps.stores.models import Store
    return Store


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
    
    # Delivery scheduling
    shipping_method = models.CharField(max_length=20, default='delivery', choices=[
        ('delivery', 'Entrega'),
        ('pickup', 'Retirada'),
    ])
    scheduled_date = models.DateField(blank=True, null=True)
    scheduled_time_slot = models.CharField(max_length=50, blank=True, null=True)
    
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


class Wishlist(models.Model):
    """User's wishlist/favorites"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wishlist'
    )
    products = models.ManyToManyField(Product, related_name='wishlisted_by', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Wishlist'
        verbose_name_plural = 'Wishlists'

    def __str__(self):
        return f"Wishlist of {self.user.email}"


class Coupon(models.Model):
    """Discount coupons - can be global or store-specific"""
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Store FK - null means global coupon valid for all stores
    # DEPRECATED: Use stores.StoreCoupon instead
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='legacy_coupons',
        null=True,
        blank=True,
        help_text="DEPRECATED: Use stores.StoreCoupon instead"
    )
    code = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Coupon'
        verbose_name_plural = 'Coupons'
        ordering = ['-created_at']
        # Code must be unique per store (or globally if store is null)
        constraints = [
            models.UniqueConstraint(
                fields=['store', 'code'],
                name='unique_coupon_code_per_store'
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.discount_value}{'%' if self.discount_type == 'percentage' else ' R$'}"

    def is_valid(self):
        """Check if coupon is valid"""
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from or now > self.valid_until:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, total):
        """Calculate discount for a given total"""
        if not self.is_valid():
            return Decimal('0.00')
        if total < self.min_purchase:
            return Decimal('0.00')
        
        if self.discount_type == 'percentage':
            discount = total * (self.discount_value / 100)
        else:
            discount = self.discount_value
        
        if self.max_discount:
            discount = min(discount, self.max_discount)
        
        return min(discount, total)

    def increment_usage(self) -> bool:
        """
        Atomically increment usage count with race condition protection.
        Returns True if increment was successful, False if usage limit reached.
        """
        from django.db.models import F
        
        # Use atomic update with condition to prevent race conditions
        if self.usage_limit:
            # Only increment if under limit
            updated = Coupon.objects.filter(
                id=self.id,
                used_count__lt=self.usage_limit
            ).update(
                used_count=F('used_count') + 1,
                updated_at=timezone.now()
            )
            return updated > 0
        else:
            # No limit, just increment
            Coupon.objects.filter(id=self.id).update(
                used_count=F('used_count') + 1,
                updated_at=timezone.now()
            )
            return True


class DeliveryZone(models.Model):
    """Delivery zones with fees (ZIP range or distance-based) - per store."""
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
    
    ZONE_TYPE_CHOICES = [
        ('distance_band', 'Distance Band'),
        ('custom_distance', 'Custom Distance Range'),
        ('zip_range', 'ZIP Code Range'),
        ('polygon', 'Custom Polygon'),
        ('time_based', 'Time-based (Isochrone)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Store FK - required for per-store zones
    # DEPRECATED: Use stores.StoreDeliveryZone instead
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='legacy_delivery_zones',
        null=True,
        blank=True,
        help_text="DEPRECATED: Use stores.StoreDeliveryZone instead"
    )
    name = models.CharField(max_length=100)
    zone_type = models.CharField(
        max_length=20, 
        choices=ZONE_TYPE_CHOICES, 
        default='distance_band',
        help_text="Type of zone definition"
    )
    distance_band = models.CharField(max_length=10, choices=DISTANCE_BAND_CHOICES, blank=True, null=True)
    zip_code_start = models.CharField(max_length=8, blank=True, null=True)
    zip_code_end = models.CharField(max_length=8, blank=True, null=True)
    min_km = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    max_km = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    # Time-based zones (isochrone)
    min_minutes = models.PositiveIntegerField(blank=True, null=True, help_text="Minimum travel time in minutes")
    max_minutes = models.PositiveIntegerField(blank=True, null=True, help_text="Maximum travel time in minutes")
    # Polygon coordinates for custom zones (GeoJSON format)
    polygon_coordinates = models.JSONField(
        default=list, 
        blank=True,
        help_text="GeoJSON coordinates for polygon zones [[lng, lat], ...]"
    )
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    min_fee = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    # Fee per km for distance-based calculation
    fee_per_km = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        blank=True, 
        null=True,
        help_text="Additional fee per km (for custom distance zones)"
    )
    estimated_days = models.PositiveIntegerField(default=1)
    estimated_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Estimated delivery time in minutes"
    )
    is_active = models.BooleanField(default=True)
    # Display color for map visualization
    color = models.CharField(max_length=7, default='#722F37', help_text="Hex color for map display")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Delivery Zone'
        verbose_name_plural = 'Delivery Zones'
        ordering = ['store', 'distance_band', 'min_km', 'zip_code_start']

    def __str__(self):
        if self.distance_band:
            label = dict(self.DISTANCE_BAND_CHOICES).get(self.distance_band, self.distance_band)
            return f"{self.name} ({label}) - R$ {self.delivery_fee}"
        if self.min_km is not None or self.max_km is not None:
            min_km = f"{self.min_km:.2f}" if self.min_km is not None else '0.00'
            max_km = f"{self.max_km:.2f}" if self.max_km is not None else '∞'
            return f"{self.name} ({min_km}-{max_km} km) - R$ {self.delivery_fee}/km"
        return f"{self.name} ({self.zip_code_start}-{self.zip_code_end}) - R$ {self.delivery_fee}"

    @classmethod
    def get_band_range(cls, band: str):
        return cls.DISTANCE_BAND_RANGES.get(band)

    @classmethod
    def get_band_for_distance(cls, distance_km: Decimal):
        if distance_km is None:
            return None
        for band, (min_km, max_km) in cls.DISTANCE_BAND_RANGES.items():
            if distance_km >= min_km and distance_km <= max_km:
                return band
        return None

    @classmethod
    def get_fee_for_zip(cls, zip_code):
        """Get delivery fee for a zip code"""
        clean_zip = ''.join(filter(str.isdigit, str(zip_code)))[:8]
        zone = cls.objects.filter(
            zip_code_start__lte=clean_zip,
            zip_code_end__gte=clean_zip,
            is_active=True
        ).exclude(zip_code_start__isnull=True).exclude(zip_code_start='').first()
        if zone:
            return {
                'fee': zone.delivery_fee,
                'estimated_days': zone.estimated_days,
                'zone_name': zone.name
            }
        return None

    @classmethod
    def get_fee_for_distance(cls, distance_km: Decimal):
        """Get delivery fee for a distance in km using fixed bands."""
        band = cls.get_band_for_distance(distance_km)
        if not band:
            return None

        zone = cls.objects.filter(
            is_active=True,
            distance_band=band
        ).order_by('-updated_at').first()
        if not zone:
            return None

        band_range = cls.get_band_range(zone.distance_band)
        return {
            'fee': zone.delivery_fee,
            'estimated_days': zone.estimated_days,
            'zone_name': zone.name,
            'distance_band': zone.distance_band,
            'min_km': band_range[0] if band_range else None,
            'max_km': band_range[1] if band_range else None,
        }


class StoreLocation(models.Model):
    """Store location used to calculate delivery distances."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=8)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Store Location'
        verbose_name_plural = 'Store Locations'

    def __str__(self):
        return self.name or f"Store ({self.zip_code})"


class ZipCodeGeo(models.Model):
    """Cached geolocation for ZIP codes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    zip_code = models.CharField(max_length=8, unique=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ZIP Geolocation'
        verbose_name_plural = 'ZIP Geolocations'

    def __str__(self):
        return self.zip_code
