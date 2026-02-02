"""
Payment API Serializers.

Serializers for StorePayment, StorePaymentGateway, and related models.
"""
from rest_framework import serializers
from apps.stores.models import (
    StorePayment,
    StorePaymentGateway,
    StorePaymentWebhookEvent,
    StoreOrder,
)


class StorePaymentGatewaySerializer(serializers.ModelSerializer):
    """Serializer for Payment Gateway."""
    
    store_name = serializers.CharField(source='store.name', read_only=True)
    gateway_type_display = serializers.CharField(source='get_gateway_type_display', read_only=True)
    
    class Meta:
        model = StorePaymentGateway
        fields = [
            'id', 'store', 'store_name', 'name', 'gateway_type', 'gateway_type_display',
            'is_enabled', 'is_sandbox', 'is_default',
            'endpoint_url', 'webhook_url', 'configuration',
            'created_at', 'updated_at', 'is_active',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'api_key': {'write_only': True},
            'api_secret': {'write_only': True},
            'access_token': {'write_only': True},
            'webhook_secret': {'write_only': True},
            'public_key': {'write_only': True},
        }


class StorePaymentGatewayListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for gateway lists (hides sensitive data)."""
    
    gateway_type_display = serializers.CharField(source='get_gateway_type_display', read_only=True)
    
    class Meta:
        model = StorePaymentGateway
        fields = [
            'id', 'name', 'gateway_type', 'gateway_type_display',
            'is_enabled', 'is_sandbox', 'is_default',
            'created_at', 'updated_at', 'is_active',
        ]


class StorePaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment."""
    
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    store_name = serializers.CharField(source='order.store.name', read_only=True)
    gateway_name = serializers.CharField(source='gateway.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    refundable_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = StorePayment
        fields = [
            'id', 'payment_id', 'external_id', 'external_reference',
            'order', 'order_number', 'store_name',
            'gateway', 'gateway_name',
            'status', 'status_display',
            'payment_method', 'payment_method_display',
            'amount', 'currency', 'fee', 'net_amount', 'refunded_amount', 'refundable_amount',
            'payer_email', 'payer_name', 'payer_document',
            'payment_url', 'qr_code', 'qr_code_base64', 'barcode', 'ticket_url',
            'expires_at', 'paid_at', 'refunded_at',
            'gateway_response', 'metadata',
            'error_code', 'error_message',
            'created_at', 'updated_at', 'is_active',
        ]
        read_only_fields = [
            'id', 'payment_id', 'external_id', 'net_amount', 'refunded_amount',
            'paid_at', 'refunded_at', 'created_at', 'updated_at',
        ]


class StorePaymentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for payment lists."""
    
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = StorePayment
        fields = [
            'id', 'payment_id', 'external_id', 'order', 'order_number',
            'status', 'status_display', 'payment_method', 'payment_method_display',
            'amount', 'currency', 'paid_at', 'created_at',
        ]


class CreatePaymentSerializer(serializers.Serializer):
    """Serializer for creating a payment."""
    
    order_id = serializers.UUIDField(required=True)
    gateway_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    payment_method = serializers.ChoiceField(
        choices=StorePayment.PaymentMethod.choices,
        required=False,
        allow_blank=True
    )
    payer_email = serializers.EmailField(required=False, allow_blank=True)
    payer_name = serializers.CharField(required=False, allow_blank=True)
    payer_document = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class ProcessPaymentSerializer(serializers.Serializer):
    """Serializer for processing a payment."""
    
    gateway_type = serializers.CharField(required=False, allow_blank=True)


class ConfirmPaymentSerializer(serializers.Serializer):
    """Serializer for confirming a payment."""
    
    external_id = serializers.CharField(required=False, allow_blank=True)
    gateway_response = serializers.JSONField(required=False, default=dict)


class FailPaymentSerializer(serializers.Serializer):
    """Serializer for failing a payment."""
    
    error_code = serializers.CharField(required=True)
    error_message = serializers.CharField(required=True)
    gateway_response = serializers.JSONField(required=False, default=dict)


class RefundPaymentSerializer(serializers.Serializer):
    """Serializer for refunding a payment."""
    
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class StorePaymentWebhookEventSerializer(serializers.ModelSerializer):
    """Serializer for Payment Webhook Event."""
    
    gateway_name = serializers.CharField(source='gateway.name', read_only=True)
    processing_status_display = serializers.CharField(source='get_processing_status_display', read_only=True)
    
    class Meta:
        model = StorePaymentWebhookEvent
        fields = [
            'id', 'gateway', 'gateway_name', 'payment', 'order',
            'event_id', 'event_type',
            'processing_status', 'processing_status_display',
            'payload', 'headers',
            'processed_at', 'retry_count', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentByOrderSerializer(serializers.Serializer):
    """Serializer for getting payments by order."""
    
    order_id = serializers.UUIDField(required=True)
