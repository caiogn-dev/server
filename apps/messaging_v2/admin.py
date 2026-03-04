from django.contrib import admin
from .models import PlatformAccount, Conversation, UnifiedMessage, MessageTemplate


@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'platform', 'phone_number', 'is_verified', 'created_at']
    list_filter = ['platform', 'is_verified', 'created_at']
    search_fields = ['name', 'phone_number']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['customer_phone', 'customer_name', 'platform', 'is_open', 'last_message_at', 'store']
    list_filter = ['platform', 'is_open', 'store']
    search_fields = ['customer_phone', 'customer_name']
    date_hierarchy = 'last_message_at'


@admin.register(UnifiedMessage)
class UnifiedMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'direction', 'status', 'conversation', 'sent_at']
    list_filter = ['direction', 'status']
    search_fields = ['text', 'external_id']
    date_hierarchy = 'created_at'


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'language', 'status', 'created_at']
    list_filter = ['status', 'category', 'language']
    search_fields = ['name', 'body']
