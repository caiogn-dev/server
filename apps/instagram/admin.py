"""
Instagram admin configuration.
"""
from django.contrib import admin
from .models import (
    InstagramAccount,
    InstagramConversation,
    InstagramMessage,
    InstagramWebhookEvent
)


@admin.register(InstagramAccount)
class InstagramAccountAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'username', 
        'status', 
        'messaging_enabled',
        'followers_count',
        'token_expires_at',
        'created_at'
    ]
    list_filter = ['status', 'messaging_enabled', 'auto_response_enabled']
    search_fields = ['name', 'username', 'instagram_account_id']
    readonly_fields = [
        'instagram_account_id',
        'instagram_user_id', 
        'masked_token',
        'token_version',
        'created_at',
        'updated_at'
    ]
    
    fieldsets = (
        ('Account Info', {
            'fields': ('name', 'username', 'instagram_account_id', 'instagram_user_id', 'facebook_page_id')
        }),
        ('App Configuration', {
            'fields': ('app_id', 'webhook_verify_token')
        }),
        ('Token', {
            'fields': ('masked_token', 'token_expires_at', 'token_version')
        }),
        ('Settings', {
            'fields': ('status', 'messaging_enabled', 'auto_response_enabled', 'human_handoff_enabled')
        }),
        ('Profile', {
            'fields': ('profile_picture_url', 'followers_count')
        }),
        ('Owner', {
            'fields': ('owner',)
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InstagramConversation)
class InstagramConversationAdmin(admin.ModelAdmin):
    list_display = [
        'participant_username',
        'account',
        'status',
        'message_count',
        'last_message_at',
        'assigned_to'
    ]
    list_filter = ['status', 'account']
    search_fields = ['participant_username', 'participant_name', 'participant_id']
    raw_id_fields = ['account', 'assigned_to']


@admin.register(InstagramMessage)
class InstagramMessageAdmin(admin.ModelAdmin):
    list_display = [
        'instagram_message_id',
        'direction',
        'message_type',
        'status',
        'sender_id',
        'text_preview',
        'created_at'
    ]
    list_filter = ['direction', 'message_type', 'status', 'account']
    search_fields = ['instagram_message_id', 'text_content', 'sender_id']
    raw_id_fields = ['account', 'conversation']
    
    def text_preview(self, obj):
        return obj.text_content[:50] + '...' if len(obj.text_content) > 50 else obj.text_content
    text_preview.short_description = 'Text'


@admin.register(InstagramWebhookEvent)
class InstagramWebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'event_id',
        'event_type',
        'processing_status',
        'account',
        'retry_count',
        'created_at'
    ]
    list_filter = ['event_type', 'processing_status']
    search_fields = ['event_id']
    readonly_fields = ['payload', 'headers', 'created_at']
