"""
Payment admin configuration.
"""
from django.contrib import admin
from .models import PaymentGateway, Payment, PaymentWebhookEvent


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'gateway_type', 'is_enabled', 'is_sandbox', 'created_at'
    ]
    list_filter = ['gateway_type', 'is_enabled', 'is_sandbox']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    filter_horizontal = ['accounts']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'payment_id', 'order', 'gateway', 'status', 'amount',
        'payment_method', 'paid_at', 'created_at'
    ]
    list_filter = ['status', 'payment_method', 'gateway']
    search_fields = ['payment_id', 'external_id', 'payer_email', 'payer_name']
    readonly_fields = [
        'id', 'payment_id', 'external_id', 'fee', 'net_amount',
        'refunded_amount', 'paid_at', 'created_at', 'updated_at'
    ]
    raw_id_fields = ['order', 'gateway']


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'event_id', 'gateway', 'event_type', 'processing_status',
        'retry_count', 'created_at', 'processed_at'
    ]
    list_filter = ['processing_status', 'event_type', 'gateway']
    search_fields = ['event_id']
    readonly_fields = ['id', 'event_id', 'created_at', 'updated_at', 'processed_at']
    raw_id_fields = ['gateway', 'payment']
