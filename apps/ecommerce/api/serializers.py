"""
E-commerce API serializers - compatible with Pastita frontend.
"""
from rest_framework import serializers
from ..models import Product, Cart, CartItem, Checkout


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock_quantity',
            'image', 'image_url', 'category', 'sku', 'is_active',
            'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        return obj.get_image_url()


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
