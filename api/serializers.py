from rest_framework import serializers
from django.contrib.auth import get_user_model
import uuid
from .models import (
    Product, Cart, CartItem, Order, OrderItem, 
    Checkout, PaymentNotification
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    class Meta:
        model = User
        fields = [
            'id', 'email', 'password', 'first_name', 'last_name',
            'phone', 'cpf', 'date_of_birth', 'profile_image',
            'address', 'city', 'state', 'zip_code', 'country',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError('E-mail é obrigatário.')
        return value.strip().lower()

    def validate_phone(self, value):
        if not value:
            return value
        digits = ''.join(char for char in value if char.isdigit())
        if len(digits) < 10 or len(digits) > 11:
            raise serializers.ValidationError('Celular inválido (10-11 dígitos).')
        return digits

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get('phone'):
                raise serializers.ValidationError({'phone': 'Celular é obrigatório.'})
        return attrs

    def create(self, validated_data):
        email = validated_data.get('email', '').strip().lower()
        phone = validated_data.get('phone')
        username = email or phone or uuid.uuid4().hex[:30]

        user = User.objects.create_user(
            username=username,
            email=email,
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=phone,
            cpf=validated_data.get('cpf'),
            date_of_birth=validated_data.get('date_of_birth'),
            profile_image=validated_data.get('profile_image'),
            address=validated_data.get('address'),
            city=validated_data.get('city'),
            state=validated_data.get('state'),
            zip_code=validated_data.get('zip_code'),
            country=validated_data.get('country', 'Brazil')
        )
        return user

    def update(self, instance, validated_data):
        """Update user, handling password specially"""
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminUserSerializer(serializers.ModelSerializer):
    """Restricted user serializer for admin dashboard"""
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'is_active', 'is_staff', 'last_login', 'date_joined',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model"""
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock_quantity',
            'image', 'category', 'sku', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CartItemSerializer(serializers.ModelSerializer):
    """Serializer for CartItem model with nested product info"""
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        write_only=True,
        source='product'
    )
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_id', 'quantity', 
            'subtotal', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_subtotal(self, obj):
        return float(obj.get_subtotal())


class CartSerializer(serializers.ModelSerializer):
    """Serializer for Cart model"""
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'items', 'total', 'item_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'items', 'total', 'item_count',
            'created_at', 'updated_at'
        ]

    def get_total(self, obj):
        return float(obj.get_total())

    def get_item_count(self, obj):
        return obj.get_item_count()


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer for OrderItem model"""
    product = ProductSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'quantity', 'price', 'subtotal', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_subtotal(self, obj):
        return float(obj.get_subtotal())


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order model"""
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'order_number', 'total_amount', 'coupon_code',
            'discount_amount', 'status',
            'shipping_address', 'shipping_city', 'shipping_state',
            'shipping_zip_code', 'shipping_country', 'notes',
            'items', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'order_number', 'coupon_code', 'discount_amount',
            'created_at', 'updated_at'
        ]


class PaymentNotificationSerializer(serializers.ModelSerializer):
    """Serializer for PaymentNotification model"""
    class Meta:
        model = PaymentNotification
        fields = [
            'id', 'notification_type', 'mercado_pago_id', 'status',
            'status_detail', 'processed', 'error_message',
            'created_at', 'processed_at'
        ]
        read_only_fields = [
            'id', 'processed', 'error_message', 'created_at', 'processed_at'
        ]


class CheckoutSerializer(serializers.ModelSerializer):
    """Serializer for Checkout model"""
    order = OrderSerializer(read_only=True)
    payment_link = serializers.URLField(read_only=True)

    class Meta:
        model = Checkout
        fields = [
            'id', 'order', 'user', 'total_amount', 'payment_status',
            'payment_method', 'mercado_pago_payment_id',
            'mercado_pago_preference_id', 'session_token', 'payment_link',
            'customer_name', 'customer_email', 'customer_phone',
            'billing_address', 'billing_city', 'billing_state',
            'billing_zip_code', 'billing_country',
            'created_at', 'updated_at', 'expires_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'session_token', 'payment_link', 'mercado_pago_preference_id',
            'created_at', 'updated_at', 'completed_at'
        ]


class CheckoutCreateSerializer(serializers.Serializer):
    """Serializer for creating a checkout from cart"""
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(max_length=20)
    billing_address = serializers.CharField()
    billing_city = serializers.CharField(max_length=100)
    billing_state = serializers.CharField(max_length=50)
    billing_zip_code = serializers.CharField(max_length=20)
    billing_country = serializers.CharField(
        max_length=100,
        default='Brazil'
    )
    payment_method = serializers.ChoiceField(
        choices=['credit_card', 'debit_card', 'pix', 'bank_transfer', 'cash']
    )


class WebhookPayloadSerializer(serializers.Serializer):
    """Serializer for validating Mercado Pago webhook payloads"""
    action = serializers.CharField(required=False, allow_blank=True)
    type = serializers.CharField(required=False, allow_blank=True)
    data = serializers.DictField(required=False)
    topic = serializers.CharField(required=False, allow_blank=True)
    id = serializers.CharField(required=False, allow_blank=True)
