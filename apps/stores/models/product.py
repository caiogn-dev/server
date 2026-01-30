"""
Store product models - StoreProduct, StoreProductVariant, StoreProductType, StoreWishlist.
"""
import uuid
from django.db import models
from apps.core.utils import build_absolute_media_url
from apps.core.models import BaseModel
from .base import Store
from .category import StoreCategory


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
    custom_fields = models.JSONField(
        default=list,
        blank=True,
        help_text="Custom field definitions for products of this type"
    )

    # Display settings
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    show_in_menu = models.BooleanField(default=True)

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


class StoreProduct(BaseModel):
    """
    Generic product model for any store type.
    Supports variants, stock management, dynamic product types, and rich metadata.
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
    product_type = models.ForeignKey(
        StoreProductType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        help_text="Product type defines custom fields for this product"
    )
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

    # Physical properties
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    weight_unit = models.CharField(max_length=10, default='kg')
    dimensions = models.JSONField(default=dict, blank=True)

    # Attributes and Tags
    attributes = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)

    # Sort order and Stats
    sort_order = models.PositiveIntegerField(default=0)
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
            return build_absolute_media_url(self.main_image.url)
        return build_absolute_media_url(self.main_image_url or '')

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

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Stock
    stock_quantity = models.IntegerField(default=0)

    # Options
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
            return build_absolute_media_url(self.image.url)
        if self.image_url:
            return build_absolute_media_url(self.image_url)
        return self.product.get_main_image_url()


class StoreWishlist(models.Model):
    """Customer wishlist for a store."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='wishlists'
    )
    customer_phone = models.CharField(max_length=20, db_index=True, blank=True, default='')
    customer_email = models.EmailField(blank=True)
    product = models.ForeignKey(
        StoreProduct,
        on_delete=models.CASCADE,
        related_name='wishlisted_by'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_wishlists'
        verbose_name = 'Wishlist Item'
        verbose_name_plural = 'Wishlist Items'
        unique_together = ['store', 'customer_phone', 'product']

    def __str__(self):
        return f"{self.customer_phone} - {self.product.name}"
