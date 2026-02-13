"""
WhatsApp admin configuration.
"""
from django.contrib import admin
from .models import WhatsAppAccount, Message, WebhookEvent, MessageTemplate


@admin.register(WhatsAppAccount)
class WhatsAppAccountAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'phone_number', 'status', 'auto_response_enabled',
        'token_version', 'created_at', 'is_active'
    ]
    list_filter = ['status', 'is_active', 'auto_response_enabled']
    search_fields = ['name', 'phone_number', 'phone_number_id']
    readonly_fields = ['id', 'token_version', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'phone_number', 'display_phone_number', 'status')
        }),
        ('WhatsApp Configuration', {
            'fields': ('phone_number_id', 'waba_id', 'webhook_verify_token')
        }),
        ('Automation', {
            'fields': (
                'default_agent', 'auto_response_enabled',
                'human_handoff_enabled'
            )
        }),
        ('Metadata', {
            'fields': ('metadata', 'owner'),
            'classes': ('collapse',)
        }),
        ('System', {
            'fields': ('id', 'token_version', 'is_active', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'account', 'direction', 'message_type', 'status',
        'from_number', 'to_number', 'created_at'
    ]
    list_filter = ['direction', 'status', 'message_type', 'account']
    search_fields = ['from_number', 'to_number', 'text_body', 'whatsapp_message_id']
    readonly_fields = [
        'id', 'whatsapp_message_id', 'sent_at', 'delivered_at',
        'read_at', 'failed_at', 'created_at', 'updated_at'
    ]
    raw_id_fields = ['account', 'conversation']


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'event_id', 'event_type', 'processing_status', 'account',
        'retry_count', 'created_at', 'processed_at'
    ]
    list_filter = ['event_type', 'processing_status', 'account']
    search_fields = ['event_id']
    readonly_fields = ['id', 'event_id', 'created_at', 'updated_at', 'processed_at']
    raw_id_fields = ['account', 'related_message']


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'account', 'language', 'category', 'status', 'created_at'
    ]
    list_filter = ['status', 'category', 'account']
    search_fields = ['name', 'template_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['account']
