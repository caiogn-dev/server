"""
Order API serializers.
"""
from rest_framework import serializers
from ..models import Order, OrderItem, OrderEvent


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer for Order Item."""
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product_id', 'product_name', 'product_sku',
            'quantity', 'unit_price', 'total_price', 'notes', 'metadata',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'total_price', 'created_at', 'updated_at']


class OrderEventSerializer(serializers.ModelSerializer):
    """Serializer for Order Event."""
    actor_name = serializers.CharField(source='actor.username', read_only=True, allow_null=True)
    
    class Meta:
        model = OrderEvent
        fields = [
            'id', 'event_type', 'description', 'old_status', 'new_status',
            'actor', 'actor_name', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order."""
    items = OrderItemSerializer(many=True, read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'account', 'account_name', 'conversation', 'order_number',
            'customer_phone', 'customer_name', 'customer_email', 'status',
            'subtotal', 'discount', 'shipping_cost', 'tax', 'total', 'currency',
            'shipping_address', 'billing_address', 'notes', 'internal_notes',
            'metadata', 'items', 'confirmed_at', 'paid_at', 'shipped_at',
            'delivered_at', 'cancelled_at', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'order_number', 'subtotal', 'total', 'confirmed_at',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at',
            'created_at', 'updated_at'
        ]


class CreateOrderItemSerializer(serializers.Serializer):
    """Serializer for creating order item."""
    product_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    product_name = serializers.CharField(max_length=255)
    product_sku = serializers.CharField(max_length=100, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)


class CreateOrderSerializer(serializers.Serializer):
    """Serializer for creating order."""
    account_id = serializers.UUIDField()
    customer_phone = serializers.CharField(max_length=20)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    items = CreateOrderItemSerializer(many=True, min_length=1)
    shipping_address = serializers.DictField(required=False, default=dict)
    billing_address = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class AddItemSerializer(serializers.Serializer):
    """Serializer for adding item to order."""
    product_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    product_name = serializers.CharField(max_length=255)
    product_sku = serializers.CharField(max_length=100, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)


class UpdateShippingSerializer(serializers.Serializer):
    """Serializer for updating shipping."""
    shipping_address = serializers.DictField()
    shipping_cost = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )


class ShipOrderSerializer(serializers.Serializer):
    """Serializer for shipping order."""
    tracking_code = serializers.CharField(max_length=100, required=False, allow_blank=True)
    carrier = serializers.CharField(max_length=100, required=False, allow_blank=True)


class CancelOrderSerializer(serializers.Serializer):
    """Serializer for cancelling order."""
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class AddNoteSerializer(serializers.Serializer):
    """Serializer for adding note."""
    note = serializers.CharField(max_length=5000)
    is_internal = serializers.BooleanField(default=False)


class PaymentConfirmationSerializer(serializers.Serializer):
    """Serializer for payment confirmation."""
    payment_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
