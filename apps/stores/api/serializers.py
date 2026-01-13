"""
Serializers for the stores API.
This is the UNIFIED e-commerce serializer module supporting all stores.

All product types are DYNAMIC - stores can create their own types with custom fields.
Products store type-specific values in the type_attributes JSONField.
"""
from rest_framework import serializers
from apps.stores.models import (
    Store, StoreIntegration, StoreWebhook, StoreCategory,
    StoreProduct, StoreProductVariant, StoreOrder, StoreOrderItem,
    StoreCustomer, StoreWishlist, StoreProductType
)


class StoreSerializer(serializers.ModelSerializer):
    """Serializer for Store model."""
    
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()
    integrations_count = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()
    orders_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Store
        fields = [
            'id', 'name', 'slug', 'description', 'store_type', 'status',
            'logo', 'logo_url', 'banner', 'banner_url',
            'primary_color', 'secondary_color',
            'email', 'phone', 'whatsapp_number',
            'address', 'city', 'state', 'zip_code', 'country',
            'latitude', 'longitude',
            'currency', 'timezone', 'tax_rate',
            'delivery_enabled', 'pickup_enabled',
            'min_order_value', 'free_delivery_threshold', 'default_delivery_fee',
            'operating_hours', 'is_open',
            'owner', 'metadata',
            'integrations_count', 'products_count', 'orders_count',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']
    
    def get_logo_url(self, obj):
        return obj.get_logo_url()
    
    def get_banner_url(self, obj):
        return obj.get_banner_url()
    
    def get_is_open(self, obj):
        return obj.is_open()
    
    def get_integrations_count(self, obj):
        return obj.integrations.filter(is_active=True).count()
    
    def get_products_count(self, obj):
        return obj.products.filter(status='active').count()
    
    def get_orders_count(self, obj):
        return obj.orders.count()


class StoreCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new store."""
    
    class Meta:
        model = Store
        fields = [
            'name', 'slug', 'description', 'store_type',
            'email', 'phone', 'whatsapp_number',
            'address', 'city', 'state', 'zip_code',
            'currency', 'timezone',
            'delivery_enabled', 'pickup_enabled',
            'min_order_value', 'default_delivery_fee'
        ]
    
    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class StoreIntegrationSerializer(serializers.ModelSerializer):
    """Serializer for StoreIntegration model."""
    
    masked_api_key = serializers.ReadOnlyField()
    masked_access_token = serializers.ReadOnlyField()
    integration_type_display = serializers.CharField(source='get_integration_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = StoreIntegration
        fields = [
            'id', 'store', 'integration_type', 'integration_type_display',
            'name', 'status', 'status_display',
            'masked_api_key', 'masked_access_token',
            'external_id', 'phone_number_id', 'waba_id',
            'webhook_url', 'webhook_verify_token',
            'settings', 'token_expires_at',
            'last_error', 'last_error_at',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_error', 'last_error_at']


class StoreIntegrationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating integrations with credentials."""
    
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    access_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    refresh_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = StoreIntegration
        fields = [
            'store', 'integration_type', 'name',
            'api_key', 'api_secret', 'access_token', 'refresh_token',
            'external_id', 'phone_number_id', 'waba_id',
            'webhook_url', 'webhook_secret', 'webhook_verify_token',
            'settings'
        ]
    
    def create(self, validated_data):
        # Extract credential fields
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)
        access_token = validated_data.pop('access_token', None)
        refresh_token = validated_data.pop('refresh_token', None)
        
        integration = StoreIntegration(**validated_data)
        
        # Set encrypted credentials
        if api_key:
            integration.api_key = api_key
        if api_secret:
            integration.api_secret = api_secret
        if access_token:
            integration.access_token = access_token
        if refresh_token:
            integration.refresh_token = refresh_token
        
        integration.status = StoreIntegration.IntegrationStatus.ACTIVE
        integration.save()
        return integration
    
    def update(self, instance, validated_data):
        # Extract credential fields
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)
        access_token = validated_data.pop('access_token', None)
        refresh_token = validated_data.pop('refresh_token', None)
        
        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update encrypted credentials only if provided
        if api_key:
            instance.api_key = api_key
        if api_secret:
            instance.api_secret = api_secret
        if access_token:
            instance.access_token = access_token
        if refresh_token:
            instance.refresh_token = refresh_token
        
        instance.save()
        return instance


class StoreWebhookSerializer(serializers.ModelSerializer):
    """Serializer for StoreWebhook model."""
    
    class Meta:
        model = StoreWebhook
        fields = [
            'id', 'store', 'name', 'url', 'secret', 'events',
            'headers', 'max_retries', 'retry_delay',
            'total_calls', 'successful_calls', 'failed_calls',
            'last_called_at', 'last_success_at', 'last_failure_at', 'last_error',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'total_calls', 'successful_calls', 'failed_calls',
            'last_called_at', 'last_success_at', 'last_failure_at', 'last_error',
            'created_at', 'updated_at'
        ]


class StoreCategorySerializer(serializers.ModelSerializer):
    """Serializer for StoreCategory model."""
    
    image_url = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCategory
        fields = [
            'id', 'store', 'name', 'slug', 'description',
            'image', 'image_url', 'parent', 'children',
            'sort_order', 'is_active', 'products_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        return obj.get_image_url()
    
    def get_products_count(self, obj):
        return obj.products.filter(status='active').count()
    
    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return StoreCategorySerializer(children, many=True).data


class StoreProductVariantSerializer(serializers.ModelSerializer):
    """Serializer for StoreProductVariant model."""
    
    effective_price = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreProductVariant
        fields = [
            'id', 'product', 'name', 'sku', 'barcode',
            'price', 'compare_at_price', 'effective_price',
            'stock_quantity', 'options',
            'image', 'image_url',
            'is_active', 'sort_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_effective_price(self, obj):
        return str(obj.get_price())
    
    def get_image_url(self, obj):
        return obj.get_image_url()


class StoreProductSerializer(serializers.ModelSerializer):
    """Serializer for StoreProduct model with dynamic product type support."""
    
    main_image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    product_type_name = serializers.CharField(source='product_type.name', read_only=True)
    product_type_slug = serializers.CharField(source='product_type.slug', read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    variants = StoreProductVariantSerializer(many=True, read_only=True)
    
    class Meta:
        model = StoreProduct
        fields = [
            'id', 'store', 'category', 'category_name',
            'product_type', 'product_type_name', 'product_type_slug', 'type_attributes',
            'name', 'slug', 'description', 'short_description',
            'sku', 'barcode',
            'price', 'compare_at_price', 'cost_price',
            'is_on_sale', 'discount_percentage',
            'track_stock', 'stock_quantity', 'low_stock_threshold',
            'allow_backorder', 'is_low_stock', 'is_in_stock',
            'status', 'featured',
            'main_image', 'main_image_url', 'images',
            'meta_title', 'meta_description',
            'weight', 'weight_unit', 'dimensions',
            'attributes', 'tags', 'sort_order',
            'view_count', 'sold_count',
            'variants',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'view_count', 'sold_count', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        return obj.get_main_image_url()


class StoreProductCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products with dynamic product type support."""
    
    class Meta:
        model = StoreProduct
        fields = [
            'store', 'category', 'product_type', 'type_attributes',
            'name', 'slug', 'description', 'short_description',
            'sku', 'barcode', 'price', 'compare_at_price', 'cost_price',
            'track_stock', 'stock_quantity', 'low_stock_threshold', 'allow_backorder',
            'status', 'featured', 'main_image', 'main_image_url', 'images',
            'meta_title', 'meta_description',
            'weight', 'weight_unit', 'dimensions',
            'attributes', 'tags', 'sort_order'
        ]
    
    def validate(self, data):
        """Validate type_attributes against product_type custom_fields."""
        product_type = data.get('product_type')
        type_attributes = data.get('type_attributes', {})
        
        if product_type and product_type.custom_fields:
            for field_def in product_type.custom_fields:
                field_name = field_def.get('name')
                is_required = field_def.get('required', False)
                
                if is_required and field_name not in type_attributes:
                    raise serializers.ValidationError({
                        'type_attributes': f"Field '{field_name}' is required for product type '{product_type.name}'"
                    })
        
        return data


# =============================================================================
# DYNAMIC PRODUCT TYPE SERIALIZERS
# =============================================================================

class StoreProductTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for dynamic product types.
    
    Product types define custom fields that products of this type should have.
    The custom_fields JSONField contains field definitions like:
    [
        {"name": "tipo", "label": "Tipo", "type": "select", "options": [{"value": "4queijos", "label": "4 Queijos"}], "required": true},
        {"name": "quantidade", "label": "Quantidade", "type": "text", "required": true},
        {"name": "calorias", "label": "Calorias", "type": "number", "required": false}
    ]
    """
    products_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreProductType
        fields = [
            'id', 'store', 'name', 'slug', 'description',
            'icon', 'image', 'custom_fields',
            'sort_order', 'is_active', 'show_in_menu',
            'products_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_products_count(self, obj):
        return obj.products.filter(status='active').count()


class StoreProductTypeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating product types."""
    
    class Meta:
        model = StoreProductType
        fields = [
            'store', 'name', 'slug', 'description',
            'icon', 'image', 'custom_fields',
            'sort_order', 'is_active', 'show_in_menu'
        ]


class StoreProductWithTypeSerializer(serializers.ModelSerializer):
    """
    Product serializer that includes dynamic product type info.
    
    The type_attributes field contains values for custom fields defined by the product_type.
    """
    main_image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    product_type_info = StoreProductTypeSerializer(source='product_type', read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    variants = StoreProductVariantSerializer(many=True, read_only=True)
    
    class Meta:
        model = StoreProduct
        fields = [
            'id', 'store', 'category', 'category_name',
            'product_type', 'product_type_info', 'type_attributes',
            'name', 'slug', 'description', 'short_description',
            'sku', 'barcode',
            'price', 'compare_at_price', 'cost_price',
            'is_on_sale', 'discount_percentage',
            'track_stock', 'stock_quantity', 'low_stock_threshold',
            'allow_backorder', 'is_low_stock', 'is_in_stock',
            'status', 'featured',
            'main_image', 'main_image_url', 'images',
            'attributes', 'tags', 'sort_order',
            'variants',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        return obj.get_main_image_url()


# =============================================================================
# WISHLIST SERIALIZERS
# =============================================================================

class StoreWishlistSerializer(serializers.ModelSerializer):
    """Serializer for user wishlist."""
    
    products = StoreProductSerializer(many=True, read_only=True)
    products_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreWishlist
        fields = ['id', 'store', 'user', 'products', 'products_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def get_products_count(self, obj):
        return obj.products.count()


class WishlistAddRemoveSerializer(serializers.Serializer):
    """Serializer for adding/removing products from wishlist."""
    
    product_id = serializers.UUIDField()


class StoreOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for StoreOrderItem model."""
    
    class Meta:
        model = StoreOrderItem
        fields = [
            'id', 'product', 'variant',
            'product_name', 'variant_name', 'sku',
            'unit_price', 'quantity', 'subtotal',
            'options', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'subtotal', 'created_at']


class StoreOrderSerializer(serializers.ModelSerializer):
    """Serializer for StoreOrder model."""
    
    items = StoreOrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    delivery_method_display = serializers.CharField(source='get_delivery_method_display', read_only=True)
    
    class Meta:
        model = StoreOrder
        fields = [
            'id', 'store', 'order_number', 'access_token',
            'customer', 'customer_name', 'customer_email', 'customer_phone',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'subtotal', 'discount', 'coupon_code', 'tax', 'delivery_fee', 'total',
            'payment_method', 'payment_id', 'payment_preference_id',
            'pix_code', 'pix_qr_code', 'pix_ticket_url',
            'delivery_method', 'delivery_method_display',
            'delivery_address', 'delivery_notes',
            'scheduled_date', 'scheduled_time',
            'tracking_code', 'tracking_url', 'carrier',
            'customer_notes', 'internal_notes',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at',
            'items', 'metadata',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'order_number', 'access_token', 'created_at', 'updated_at',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at'
        ]


class StoreOrderCreateSerializer(serializers.Serializer):
    """Serializer for creating orders."""
    
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(max_length=20)
    customer_notes = serializers.CharField(required=False, allow_blank=True)
    
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1
    )
    
    delivery_method = serializers.ChoiceField(
        choices=['delivery', 'pickup', 'digital'],
        default='delivery'
    )
    delivery_address = serializers.DictField(required=False)
    delivery_notes = serializers.CharField(required=False, allow_blank=True)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    scheduled_date = serializers.DateField(required=False)
    scheduled_time = serializers.CharField(required=False, allow_blank=True)
    
    coupon_code = serializers.CharField(required=False, allow_blank=True)


class StoreOrderUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating order status."""
    
    class Meta:
        model = StoreOrder
        fields = [
            'status', 'payment_status', 'internal_notes',
            'tracking_code', 'tracking_url', 'carrier'
        ]


class StoreCustomerSerializer(serializers.ModelSerializer):
    """Serializer for StoreCustomer model."""
    
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    default_address = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCustomer
        fields = [
            'id', 'store', 'user', 'user_email', 'user_name',
            'phone', 'whatsapp',
            'instagram', 'twitter', 'facebook',
            'addresses', 'default_address_index', 'default_address',
            'total_orders', 'total_spent', 'last_order_at',
            'tags', 'notes',
            'accepts_marketing', 'marketing_opt_in_at',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'total_orders', 'total_spent', 'last_order_at',
            'created_at', 'updated_at'
        ]
    
    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
    
    def get_default_address(self, obj):
        return obj.get_default_address()


class StoreStatsSerializer(serializers.Serializer):
    """Serializer for store statistics."""
    
    orders = serializers.DictField()
    revenue = serializers.DictField()
    products = serializers.DictField()
    customers = serializers.DictField()
    daily_orders = serializers.ListField()


# =============================================================================
# CART SERIALIZERS
# =============================================================================

from apps.stores.models import StoreCart, StoreCartItem, StoreCartComboItem, StoreCombo, StoreComboItem, StoreProductType


class StoreCartItemSerializer(serializers.ModelSerializer):
    """Serializer for cart items."""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    variant_name = serializers.CharField(source='variant.name', read_only=True, allow_null=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = StoreCartItem
        fields = [
            'id', 'product', 'product_name', 'product_image',
            'variant', 'variant_name',
            'quantity', 'unit_price', 'subtotal',
            'options', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_product_image(self, obj):
        return obj.product.get_main_image_url()


class StoreCartComboItemSerializer(serializers.ModelSerializer):
    """Serializer for cart combo items."""
    
    combo_name = serializers.CharField(source='combo.name', read_only=True)
    combo_image = serializers.SerializerMethodField()
    unit_price = serializers.DecimalField(source='combo.price', max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = StoreCartComboItem
        fields = [
            'id', 'combo', 'combo_name', 'combo_image',
            'quantity', 'unit_price', 'subtotal',
            'customizations', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_combo_image(self, obj):
        return obj.combo.get_image_url()


class StoreCartSerializer(serializers.ModelSerializer):
    """Serializer for shopping cart."""
    
    items = StoreCartItemSerializer(many=True, read_only=True)
    combo_items = StoreCartComboItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    
    class Meta:
        model = StoreCart
        fields = [
            'id', 'store', 'store_name', 'user',
            'items', 'combo_items',
            'subtotal', 'item_count', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class AddToCartSerializer(serializers.Serializer):
    """Serializer for adding items to cart."""
    
    product_id = serializers.UUIDField(required=False)
    combo_id = serializers.UUIDField(required=False)
    variant_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    options = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    
    def validate(self, data):
        if not data.get('product_id') and not data.get('combo_id'):
            raise serializers.ValidationError("product_id ou combo_id é obrigatório")
        return data


class UpdateCartItemSerializer(serializers.Serializer):
    """Serializer for updating cart item quantity."""
    
    quantity = serializers.IntegerField(min_value=0)


# =============================================================================
# CHECKOUT SERIALIZERS
# =============================================================================

class CheckoutSerializer(serializers.Serializer):
    """Serializer for checkout process."""
    
    # Customer info
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(max_length=20)
    
    # Delivery info
    delivery_method = serializers.ChoiceField(choices=['delivery', 'pickup'], default='delivery')
    delivery_address = serializers.DictField(required=False)
    delivery_notes = serializers.CharField(required=False, allow_blank=True, default='')
    distance_km = serializers.DecimalField(max_digits=7, decimal_places=2, required=False, allow_null=True)
    
    # Payment
    payment_method = serializers.ChoiceField(choices=['pix', 'credit_card', 'debit_card', 'cash', 'card'], default='pix')
    
    # Coupon
    coupon_code = serializers.CharField(required=False, allow_blank=True, default='')
    
    # Notes
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class CheckoutResponseSerializer(serializers.Serializer):
    """Serializer for checkout response."""
    
    success = serializers.BooleanField()
    order_id = serializers.UUIDField(required=False)
    order_number = serializers.CharField(required=False)
    
    # Payment info
    payment_id = serializers.CharField(required=False)
    payment_status = serializers.CharField(required=False)
    
    # PIX data
    pix_code = serializers.CharField(required=False)
    pix_qr_code = serializers.CharField(required=False)
    pix_expiration = serializers.DateTimeField(required=False)
    
    # Redirect URL (for card payments)
    redirect_url = serializers.URLField(required=False)
    
    # Totals
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    
    # Error
    error = serializers.CharField(required=False)


# =============================================================================
# CATALOG SERIALIZERS
# =============================================================================

class StoreProductTypeSerializer(serializers.ModelSerializer):
    """Serializer for product types."""
    
    class Meta:
        model = StoreProductType
        fields = [
            'id', 'name', 'slug', 'description',
            'icon', 'image', 'custom_fields',
            'sort_order', 'is_active', 'show_in_menu',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StoreComboItemSerializer(serializers.ModelSerializer):
    """Serializer for combo items."""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreComboItem
        fields = [
            'id', 'product', 'product_name', 'product_image',
            'variant', 'quantity',
            'allow_customization', 'customization_options'
        ]
    
    def get_product_image(self, obj):
        return obj.product.get_main_image_url()


class StoreComboSerializer(serializers.ModelSerializer):
    """Serializer for combos."""
    
    items = StoreComboItemSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    savings = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    savings_percentage = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = StoreCombo
        fields = [
            'id', 'store', 'name', 'slug', 'description',
            'price', 'compare_at_price', 'savings', 'savings_percentage',
            'image', 'image_url',
            'is_active', 'featured',
            'track_stock', 'stock_quantity',
            'items',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        return obj.get_image_url()


class StoreCatalogSerializer(serializers.Serializer):
    """Serializer for store catalog."""
    
    store = StoreSerializer()
    categories = StoreCategorySerializer(many=True)
    product_types = StoreProductTypeSerializer(many=True)
    products = StoreProductSerializer(many=True)
    combos = StoreComboSerializer(many=True)
    featured_products = StoreProductSerializer(many=True)


# =============================================================================
# COUPON SERIALIZERS
# =============================================================================

from apps.stores.models import StoreCoupon, StoreDeliveryZone, StoreOrderComboItem


class StoreCouponSerializer(serializers.ModelSerializer):
    """Serializer for store coupons."""
    
    discount_type_display = serializers.CharField(source='get_discount_type_display', read_only=True)
    is_valid_now = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCoupon
        fields = [
            'id', 'store', 'code', 'description',
            'discount_type', 'discount_type_display', 'discount_value',
            'min_purchase', 'max_discount',
            'usage_limit', 'usage_limit_per_user', 'used_count',
            'is_active', 'valid_from', 'valid_until',
            'first_order_only',
            'applicable_categories', 'applicable_products',
            'is_valid_now',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'used_count', 'created_at', 'updated_at']
    
    def get_is_valid_now(self, obj):
        valid, _ = obj.is_valid()
        return valid


class StoreCouponCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating coupons."""
    
    class Meta:
        model = StoreCoupon
        fields = [
            'store', 'code', 'description',
            'discount_type', 'discount_value',
            'min_purchase', 'max_discount',
            'usage_limit', 'usage_limit_per_user',
            'is_active', 'valid_from', 'valid_until',
            'first_order_only',
            'applicable_categories', 'applicable_products'
        ]


class CouponValidateSerializer(serializers.Serializer):
    """Serializer for coupon validation request."""
    
    code = serializers.CharField(max_length=50)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)


class CouponValidateResponseSerializer(serializers.Serializer):
    """Serializer for coupon validation response."""
    
    valid = serializers.BooleanField()
    coupon_id = serializers.UUIDField(required=False)
    code = serializers.CharField(required=False)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount_type = serializers.CharField(required=False)
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    error = serializers.CharField(required=False)


# =============================================================================
# DELIVERY ZONE SERIALIZERS
# =============================================================================

class StoreDeliveryZoneSerializer(serializers.ModelSerializer):
    """Serializer for delivery zones."""
    
    zone_type_display = serializers.CharField(source='get_zone_type_display', read_only=True)
    distance_band_display = serializers.SerializerMethodField()
    distance_label = serializers.SerializerMethodField()  # Alias for frontend compatibility
    store_name = serializers.CharField(source='store.name', read_only=True)
    
    class Meta:
        model = StoreDeliveryZone
        fields = [
            'id', 'store', 'store_name', 'name',
            'zone_type', 'zone_type_display',
            'distance_band', 'distance_band_display', 'distance_label',
            'min_km', 'max_km',
            'zip_code_start', 'zip_code_end',
            'min_minutes', 'max_minutes',
            'polygon_coordinates',
            'delivery_fee', 'min_fee', 'fee_per_km',
            'estimated_minutes', 'estimated_days',
            'color', 'is_active', 'sort_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_distance_band_display(self, obj):
        if obj.distance_band:
            return dict(StoreDeliveryZone.DISTANCE_BAND_CHOICES).get(obj.distance_band, obj.distance_band)
        return None
    
    def get_distance_label(self, obj):
        """Alias for distance_band_display for frontend compatibility."""
        return self.get_distance_band_display(obj)


class StoreDeliveryZoneCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating delivery zones."""
    
    class Meta:
        model = StoreDeliveryZone
        fields = [
            'store', 'name', 'zone_type',
            'distance_band', 'min_km', 'max_km',
            'zip_code_start', 'zip_code_end',
            'min_minutes', 'max_minutes',
            'polygon_coordinates',
            'delivery_fee', 'min_fee', 'fee_per_km',
            'estimated_minutes', 'estimated_days',
            'color', 'is_active', 'sort_order'
        ]


class DeliveryFeeRequestSerializer(serializers.Serializer):
    """Serializer for delivery fee calculation request."""
    
    distance_km = serializers.DecimalField(max_digits=7, decimal_places=2, required=False)
    zip_code = serializers.CharField(max_length=10, required=False)
    lat = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    lng = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)


class DeliveryFeeResponseSerializer(serializers.Serializer):
    """Serializer for delivery fee calculation response."""
    
    fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    zone_id = serializers.UUIDField(required=False)
    zone_name = serializers.CharField(required=False)
    estimated_minutes = serializers.IntegerField(required=False)
    available = serializers.BooleanField(default=True)
    error = serializers.CharField(required=False)


# =============================================================================
# ORDER COMBO ITEM SERIALIZER
# =============================================================================

class StoreOrderComboItemSerializer(serializers.ModelSerializer):
    """Serializer for order combo items."""
    
    class Meta:
        model = StoreOrderComboItem
        fields = [
            'id', 'combo', 'combo_name',
            'unit_price', 'quantity', 'subtotal',
            'customizations', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'subtotal', 'created_at']


# Update StoreOrderSerializer to include combo_items
class StoreOrderFullSerializer(serializers.ModelSerializer):
    """Full serializer for StoreOrder including combo items."""
    
    items = StoreOrderItemSerializer(many=True, read_only=True)
    combo_items = StoreOrderComboItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    delivery_method_display = serializers.CharField(source='get_delivery_method_display', read_only=True)
    
    class Meta:
        model = StoreOrder
        fields = [
            'id', 'store', 'order_number', 'access_token',
            'customer', 'customer_name', 'customer_email', 'customer_phone',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'subtotal', 'discount', 'coupon_code', 'tax', 'delivery_fee', 'total',
            'payment_method', 'payment_id', 'payment_preference_id',
            'pix_code', 'pix_qr_code', 'pix_ticket_url',
            'delivery_method', 'delivery_method_display',
            'delivery_address', 'delivery_notes',
            'scheduled_date', 'scheduled_time',
            'tracking_code', 'tracking_url', 'carrier',
            'customer_notes', 'internal_notes',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at',
            'items', 'combo_items', 'metadata',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'order_number', 'access_token', 'created_at', 'updated_at',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at'
        ]


# =============================================================================
# PUBLIC CATALOG SERIALIZERS (for storefront)
# =============================================================================

class PublicProductSerializer(serializers.ModelSerializer):
    """Public product serializer for storefront (no sensitive data)."""
    
    main_image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    
    class Meta:
        model = StoreProduct
        fields = [
            'id', 'name', 'slug', 'description', 'short_description',
            'price', 'compare_at_price',
            'is_on_sale', 'discount_percentage',
            'stock_quantity', 'is_in_stock',
            'status', 'featured',
            'main_image_url', 'images',
            'category', 'category_name', 'category_slug',
            'attributes', 'tags'
        ]
    
    def get_main_image_url(self, obj):
        return obj.get_main_image_url()


class PublicComboSerializer(serializers.ModelSerializer):
    """Public combo serializer for storefront."""
    
    items = StoreComboItemSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    savings = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    savings_percentage = serializers.IntegerField(read_only=True)
    is_in_stock = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCombo
        fields = [
            'id', 'name', 'slug', 'description',
            'price', 'compare_at_price', 'savings', 'savings_percentage',
            'image_url',
            'is_active', 'featured',
            'stock_quantity', 'is_in_stock',
            'items'
        ]
    
    def get_image_url(self, obj):
        return obj.get_image_url()
    
    def get_is_in_stock(self, obj):
        if not obj.track_stock:
            return True
        return obj.stock_quantity > 0


class PublicCatalogSerializer(serializers.Serializer):
    """Public catalog serializer for storefront."""
    
    store = serializers.SerializerMethodField()
    categories = StoreCategorySerializer(many=True)
    product_types = StoreProductTypeSerializer(many=True)
    products = PublicProductSerializer(many=True)
    products_by_category = serializers.DictField()
    combos = PublicComboSerializer(many=True)
    combos_destaque = PublicComboSerializer(many=True)
    featured_products = PublicProductSerializer(many=True)
    
    def get_store(self, obj):
        store = obj.get('store')
        if store:
            return {
                'id': str(store.id),
                'name': store.name,
                'slug': store.slug,
                'description': store.description,
                'logo_url': store.get_logo_url(),
                'primary_color': store.primary_color,
                'secondary_color': store.secondary_color,
                'phone': store.phone,
                'whatsapp_number': store.whatsapp_number,
                'address': store.address,
                'city': store.city,
                'state': store.state,
                'latitude': str(store.latitude) if store.latitude else None,
                'longitude': str(store.longitude) if store.longitude else None,
                'delivery_enabled': store.delivery_enabled,
                'pickup_enabled': store.pickup_enabled,
                'min_order_value': str(store.min_order_value),
                'default_delivery_fee': str(store.default_delivery_fee),
                'is_open': store.is_open(),
            }
        return None
