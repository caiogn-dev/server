from django.contrib import admin
from .models import (
    MessengerAccount, MessengerProfile, MessengerConversation,
    MessengerMessage, MessengerBroadcast, MessengerSponsoredMessage,
    MessengerExtension, MessengerWebhookLog
)


@admin.register(MessengerAccount)
class MessengerAccountAdmin(admin.ModelAdmin):
    list_display = ['page_name', 'user', 'category', 'followers_count', 'is_active']
    list_filter = ['is_active', 'webhook_verified', 'created_at']
    search_fields = ['page_name', 'page_id', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']


@admin.register(MessengerProfile)
class MessengerProfileAdmin(admin.ModelAdmin):
    list_display = ['account', 'greeting_text_preview', 'updated_at']
    
    def greeting_text_preview(self, obj):
        return obj.greeting_text[:50] + '...' if len(obj.greeting_text) > 50 else obj.greeting_text
    greeting_text_preview.short_description = 'Greeting'


@admin.register(MessengerConversation)
class MessengerConversationAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'account', 'unread_count', 'last_message_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['participant_name', 'psid']


@admin.register(MessengerMessage)
class MessengerMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'message_type', 'content_preview', 'is_from_page', 'created_at']
    list_filter = ['message_type', 'is_from_page', 'is_read', 'created_at']
    search_fields = ['content']
    readonly_fields = ['created_at']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(MessengerBroadcast)
class MessengerBroadcastAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'status', 'total_recipients', 'sent_count', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name']


@admin.register(MessengerSponsoredMessage)
class MessengerSponsoredMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'status', 'impressions', 'clicks', 'spent']
    list_filter = ['status', 'created_at']
    search_fields = ['name']


@admin.register(MessengerExtension)
class MessengerExtensionAdmin(admin.ModelAdmin):
    list_display = ['name', 'extension_type', 'url', 'is_active']
    list_filter = ['extension_type', 'is_active', 'created_at']


@admin.register(MessengerWebhookLog)
class MessengerWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['object_type', 'is_processed', 'created_at']
    list_filter = ['object_type', 'is_processed', 'created_at']
    readonly_fields = ['created_at']