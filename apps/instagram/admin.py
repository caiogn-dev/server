"""Instagram admin - Simplificado.

Mantidos apenas os modelos principais visíveis no admin.
"""
from django.contrib import admin
from .models import (
    InstagramAccount, InstagramConversation, InstagramMessage,
    InstagramCatalog, InstagramProduct
)


@admin.register(InstagramAccount)
class InstagramAccountAdmin(admin.ModelAdmin):
    list_display = ['username', 'user', 'followers_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['username', 'user__email']


@admin.register(InstagramConversation)
class InstagramConversationAdmin(admin.ModelAdmin):
    list_display = ['participant_username', 'account', 'unread_count', 'last_message_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['participant_username']


@admin.register(InstagramMessage)
class InstagramMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'message_type', 'is_from_business', 'created_at']
    list_filter = ['message_type', 'is_from_business', 'created_at']
    search_fields = ['content']


@admin.register(InstagramCatalog)
class InstagramCatalogAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']


@admin.register(InstagramProduct)
class InstagramProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'catalog', 'price', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
