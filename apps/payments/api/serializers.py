"""
Payment API serializers.
"""
from rest_framework import serializers
from ..models import Payment, PaymentGateway, PaymentWebhookEvent


class PaymentGatewaySerializer(serializers.ModelSerializer):
    """Serializer for Payment Gateway."""
    
    class Meta:
        model = PaymentGateway
        fields = [
            'id', 'name', 'gateway_type', 'is_enabled', 'is_sandbox',
            'endpoint_url', 'webhook_url', 'configuration',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment."""
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    gateway_name = serializers.CharField(source='gateway.name', read_only=True, allow_null=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'order_number', 'gateway', 'gateway_name',
            'payment_id', 'external_id', 'status', 'payment_method',
            'amount', 'currency', 'fee', 'net_amount', 'refunded_amount',
            'payer_email', 'payer_name', 'payer_document',
            'payment_url', 'qr_code', 'barcode', 'expires_at', 'paid_at',
            'error_code', 'error_message', 'metadata',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'payment_id', 'external_id', 'fee', 'net_amount',
            'refunded_amount', 'paid_at', 'error_code', 'error_message',
            'created_at', 'updated_at'
        ]


class CreatePaymentSerializer(serializers.Serializer):
    """Serializer for creating payment."""
    order_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    gateway_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(
        choices=Payment.PaymentMethod.choices,
        required=False,
        allow_blank=True
    )
    payer_email = serializers.EmailField(required=False, allow_blank=True)
    payer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    payer_document = serializers.CharField(max_length=50, required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)


class ProcessPaymentSerializer(serializers.Serializer):
    """Serializer for processing payment."""
    gateway_type = serializers.ChoiceField(
        choices=PaymentGateway.GatewayType.choices,
        required=False,
        allow_blank=True
    )


class ConfirmPaymentSerializer(serializers.Serializer):
    """Serializer for confirming payment."""
    external_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    gateway_response = serializers.DictField(required=False, default=dict)


class FailPaymentSerializer(serializers.Serializer):
    """Serializer for failing payment."""
    error_code = serializers.CharField(max_length=50)
    error_message = serializers.CharField(max_length=500)
    gateway_response = serializers.DictField(required=False, default=dict)


class RefundPaymentSerializer(serializers.Serializer):
    """Serializer for refunding payment."""
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PaymentWebhookEventSerializer(serializers.ModelSerializer):
    """Serializer for Payment Webhook Event."""
    gateway_name = serializers.CharField(source='gateway.name', read_only=True)
    
    class Meta:
        model = PaymentWebhookEvent
        fields = [
            'id', 'gateway', 'gateway_name', 'payment', 'event_id',
            'event_type', 'processing_status', 'processed_at',
            'retry_count', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
