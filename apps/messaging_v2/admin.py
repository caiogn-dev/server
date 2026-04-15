from django.contrib import admin
from .models import PlatformAccount, Conversation, UnifiedMessage, MessageTemplate


@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'platform', 'user', 'phone_number', 'page_name',
        'status', 'is_active', 'is_verified', 'created_at'
    ]
    list_filter = ['platform', 'status', 'is_active', 'is_verified', 'created_at']
    search_fields = [
        'name', 'phone_number', 'phone_number_id', 'waba_id',
        'page_name', 'page_id', 'instagram_account_id', 'user__email'
    ]
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('user', 'platform', 'name', 'status', 'is_active')
        }),
        ('WhatsApp Business', {
            'fields': ('phone_number_id', 'waba_id', 'phone_number', 'display_phone_number'),
            'classes': ('collapse',)
        }),
        ('Messenger', {
            'fields': ('page_id', 'page_name'),
            'classes': ('collapse',)
        }),
        ('Instagram', {
            'fields': ('instagram_account_id',),
            'classes': ('collapse',)
        }),
        ('Configurações', {
            'fields': ('access_token', 'webhook_verify_token', 'webhook_verified')
        }),
        ('IA e Automação', {
            'fields': ('auto_response_enabled', 'human_handoff_enabled', 'default_agent_id')
        }),
        ('Metadados', {
            'fields': ('category', 'followers_count', 'is_verified', 'last_sync_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        'customer_name', 'customer_phone', 'platform', 'platform_account',
        'is_open', 'unread_count', 'last_message_at'
    ]
    list_filter = ['platform', 'is_open', 'created_at']
    search_fields = ['customer_phone', 'customer_name', 'customer_id']
    date_hierarchy = 'last_message_at'
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UnifiedMessage)
class UnifiedMessageAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'conversation', 'direction', 'message_type',
        'status', 'text_preview', 'created_at'
    ]
    list_filter = ['direction', 'status', 'message_type', 'created_at']
    search_fields = ['text', 'external_id', 'conversation__customer_name']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at']
    
    def text_preview(self, obj):
        return obj.text[:50] + '...' if obj.text and len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Texto'


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'platform_account', 'category', 'language',
        'status', 'created_at'
    ]
    list_filter = ['status', 'category', 'language', 'created_at']
    search_fields = ['name', 'body', 'external_id']
    readonly_fields = ['created_at', 'updated_at']
