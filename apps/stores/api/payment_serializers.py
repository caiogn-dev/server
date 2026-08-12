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
    tem_credencial = serializers.SerializerMethodField()
    token_expirado = serializers.BooleanField(source='token_vencido', read_only=True)

    def get_tem_credencial(self, obj) -> bool:
        """A tela precisa distinguir "sem gateway" de "gateway sem token"."""
        return bool(obj.access_token)

    class Meta:
        model = StorePaymentGateway
        fields = [
            'id', 'store', 'store_name', 'name', 'gateway_type', 'gateway_type_display',
            'is_enabled', 'is_sandbox', 'is_default',
            'endpoint_url', 'webhook_url', 'configuration',
            # Credenciais: entram, nunca saem. Antes elas nem estavam aqui e o
            # `extra_kwargs` abaixo era letra morta — o endpoint existia e não
            # gravava o token, então o lojista não tinha como configurar a conta
            # dele e o dinheiro continuava indo para a plataforma.
            'api_key', 'api_secret', 'access_token', 'webhook_secret', 'public_key',
            # Só o estado, para a tela saber o que mostrar.
            'connection_type', 'tem_credencial', 'token_expirado',
            'created_at', 'updated_at', 'is_active',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'connection_type']
        extra_kwargs = {
            'api_key': {'write_only': True, 'required': False, 'allow_blank': True},
            'api_secret': {'write_only': True, 'required': False, 'allow_blank': True},
            'access_token': {'write_only': True, 'required': False, 'allow_blank': True},
            'webhook_secret': {'write_only': True, 'required': False, 'allow_blank': True},
            'public_key': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def update(self, instance, validated_data):
        # Campo de segredo em branco = "não mexi nisso". Sem esta guarda, editar
        # o nome do gateway apagaria a credencial e derrubaria o checkout.
        for campo in ('api_key', 'api_secret', 'access_token', 'webhook_secret', 'public_key'):
            if campo in validated_data and not validated_data[campo]:
                validated_data.pop(campo)
        return super().update(instance, validated_data)


class StorePaymentGatewayListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for gateway lists (hides sensitive data)."""
    
    gateway_type_display = serializers.CharField(source='get_gateway_type_display', read_only=True)
    tem_credencial = serializers.SerializerMethodField()
    token_expirado = serializers.BooleanField(source='token_vencido', read_only=True)

    def get_tem_credencial(self, obj) -> bool:
        return bool(obj.access_token)

    class Meta:
        model = StorePaymentGateway
        fields = [
            'id', 'name', 'gateway_type', 'gateway_type_display',
            'is_enabled', 'is_sandbox', 'is_default',
            # Estado da conexão — nunca o segredo.
            'connection_type', 'tem_credencial', 'token_expirado',
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
    # Cobrança avulsa não tem pedido para se identificar: o link, o rótulo e o
    # pagador SÃO a identidade dela. Sem isso a tela lista valores anônimos.
    description = serializers.SerializerMethodField()

    class Meta:
        model = StorePayment
        fields = [
            'id', 'payment_id', 'external_id', 'order', 'order_number',
            'status', 'status_display', 'payment_method', 'payment_method_display',
            'amount', 'currency', 'paid_at', 'created_at',
            'payment_url', 'payer_name', 'payer_email', 'expires_at', 'description',
        ]

    def get_description(self, obj):
        return (obj.metadata or {}).get('description') or ''


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
