"""
E-commerce API serializers - compatible with Pastita frontend.
"""
from rest_framework import serializers
from ..models import Product, Cart, CartItem, Checkout, Wishlist, Coupon, DeliveryZone, StoreLocation


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock_quantity',
            'image', 'image_url', 'category', 'sku', 'is_active',
            'metadata', 'created_at', 'updated_at', 'is_favorited'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        return obj.get_image_url()

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.wishlisted_by.filter(user=request.user).exists()
        return False


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.UUIDField(write_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_id', 'quantity', 'subtotal',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_subtotal(self, obj):
        return float(obj.get_subtotal())


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'session_key', 'phone_number',
            'items', 'total', 'item_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_total(self, obj):
        return float(obj.get_total())

    def get_item_count(self, obj):
        return obj.get_item_count()


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    item_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False)
    quantity = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        if not attrs.get('item_id') and not attrs.get('product_id'):
            raise serializers.ValidationError('item_id or product_id is required.')
        return attrs


class RemoveFromCartSerializer(serializers.Serializer):
    item_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if not attrs.get('item_id') and not attrs.get('product_id'):
            raise serializers.ValidationError('item_id or product_id is required.')
        return attrs


class CheckoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkout
        fields = [
            'id', 'cart', 'order', 'user', 'total_amount',
            'payment_status', 'session_token', 'payment_link',
            'pix_code', 'pix_qr_code',
            'customer_name', 'customer_email', 'customer_phone',
            'shipping_address', 'shipping_city', 'shipping_state', 'shipping_zip_code',
            'mercado_pago_preference_id', 'mercado_pago_payment_id',
            'created_at', 'updated_at', 'expires_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'session_token', 'payment_link', 'pix_code', 'pix_qr_code',
            'mercado_pago_preference_id', 'mercado_pago_payment_id',
            'created_at', 'updated_at', 'completed_at'
        ]


class CreateCheckoutSerializer(serializers.Serializer):
    """Serializer for creating checkout from cart"""
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(max_length=20)
    shipping_address = serializers.CharField(required=False, allow_blank=True)
    shipping_city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    shipping_state = serializers.CharField(max_length=50, required=False, allow_blank=True)
    shipping_zip_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    shipping_method = serializers.ChoiceField(
        choices=[('delivery', 'Entrega'), ('pickup', 'Retirada')],
        default='delivery',
        required=False
    )
    scheduled_date = serializers.DateField(required=False, allow_null=True)
    scheduled_time_slot = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)


class WishlistSerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Wishlist
        fields = ['id', 'products', 'product_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_count(self, obj):
        return obj.products.count()


class CouponSerializer(serializers.ModelSerializer):
    is_valid_now = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            'id', 'store', 'store_name', 'code', 'description', 'discount_type', 'discount_value',
            'min_purchase', 'max_discount', 'usage_limit', 'used_count',
            'is_active', 'is_valid_now', 'valid_from', 'valid_until',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'store_name', 'used_count', 'created_at', 'updated_at']

    def get_is_valid_now(self, obj):
        return obj.is_valid()
    
    def get_store_name(self, obj):
        return obj.store.name if obj.store else None


class ValidateCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class DeliveryFeeSerializer(serializers.Serializer):
    zip_code = serializers.CharField(max_length=10)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)


class DeliveryZoneSerializer(serializers.ModelSerializer):
    distance_label = serializers.SerializerMethodField()
    min_km = serializers.SerializerMethodField()
    max_km = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryZone
        fields = [
            'id', 'store', 'store_name', 'name', 'zone_type', 'distance_band', 'distance_label',
            'min_km', 'max_km', 'min_minutes', 'max_minutes',
            'delivery_fee', 'fee_per_km', 'estimated_days', 'estimated_minutes',
            'color', 'polygon_coordinates', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'store_name', 'distance_label', 'min_km', 'max_km', 'created_at', 'updated_at']

    def get_distance_label(self, obj):
        return dict(DeliveryZone.DISTANCE_BAND_CHOICES).get(obj.distance_band, '')

    def get_min_km(self, obj):
        if obj.min_km is not None:
            return obj.min_km
        band_range = DeliveryZone.get_band_range(obj.distance_band)
        return band_range[0] if band_range else None

    def get_max_km(self, obj):
        if obj.max_km is not None:
            return obj.max_km
        band_range = DeliveryZone.get_band_range(obj.distance_band)
        return band_range[1] if band_range else None
    
    def get_store_name(self, obj):
        return obj.store.name if obj.store else None

    def validate(self, attrs):
        if self.instance is None and not attrs.get('distance_band') and not attrs.get('zone_type'):
            raise serializers.ValidationError({'distance_band': 'Selecione uma faixa de distancia ou tipo de zona.'})
        return attrs


class StoreLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreLocation
        fields = [
            'id', 'name', 'zip_code', 'address', 'city', 'state',
            'latitude', 'longitude', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'latitude', 'longitude', 'created_at', 'updated_at']
