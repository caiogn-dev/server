from django.contrib import admin
from .models import (
    InstagramAccount, InstagramMedia, InstagramMediaItem,
    InstagramProductTag, InstagramCatalog, InstagramProduct,
    InstagramLive, InstagramLiveComment, InstagramConversation,
    InstagramMessage, InstagramScheduledPost, InstagramInsight,
    InstagramWebhookLog
)


@admin.register(InstagramAccount)
class InstagramAccountAdmin(admin.ModelAdmin):
    list_display = ['username', 'user', 'followers_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'is_verified', 'created_at']
    search_fields = ['username', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']


@admin.register(InstagramMedia)
class InstagramMediaAdmin(admin.ModelAdmin):
    list_display = ['account', 'media_type', 'caption_preview', 'status', 'created_at']
    list_filter = ['media_type', 'status', 'created_at']
    search_fields = ['caption', 'account__username']
    readonly_fields = ['created_at', 'updated_at']
    
    def caption_preview(self, obj):
        return obj.caption[:50] + '...' if len(obj.caption) > 50 else obj.caption
    caption_preview.short_description = 'Caption'


@admin.register(InstagramConversation)
class InstagramConversationAdmin(admin.ModelAdmin):
    list_display = ['participant_username', 'account', 'unread_count', 'last_message_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['participant_username', 'participant_name']


@admin.register(InstagramMessage)
class InstagramMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'message_type', 'content_preview', 'is_from_business', 'created_at']
    list_filter = ['message_type', 'is_from_business', 'is_read', 'created_at']
    search_fields = ['content']
    readonly_fields = ['created_at']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(InstagramLive)
class InstagramLiveAdmin(admin.ModelAdmin):
    list_display = ['title', 'account', 'status', 'viewers_count', 'started_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description']


@admin.register(InstagramCatalog)
class InstagramCatalogAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'catalog_id']


@admin.register(InstagramProduct)
class InstagramProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'catalog', 'price', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'product_id']


@admin.register(InstagramScheduledPost)
class InstagramScheduledPostAdmin(admin.ModelAdmin):
    list_display = ['account', 'media_type', 'schedule_time', 'status']
    list_filter = ['status', 'media_type', 'created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InstagramWebhookLog)
class InstagramWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['object_type', 'field', 'is_processed', 'created_at']
    list_filter = ['object_type', 'is_processed', 'created_at']
    readonly_fields = ['created_at']