"""Messaging admin - LEGACY (Messenger específico).

Use messaging_v2 para a versão unificada (WhatsApp, Messenger, etc).
"""
from django.contrib import admin
from .models import PlatformAccount, UnifiedConversation, UnifiedMessage, UnifiedTemplate


@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'platform', 'is_active', 'created_at']
    list_filter = ['platform', 'is_active', 'created_at']
    search_fields = ['name']

    def get_model_perms(self, request):
        """Não mostrar no índice do admin - usar messaging_v2."""
        return {}


@admin.register(UnifiedConversation)
class UnifiedConversationAdmin(admin.ModelAdmin):
    list_display = ['customer_name', 'platform_account', 'status']

    def get_model_perms(self, request):
        return {}


@admin.register(UnifiedMessage)
class UnifiedMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'direction', 'created_at']

    def get_model_perms(self, request):
        return {}


@admin.register(UnifiedTemplate)
class UnifiedTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'created_at']

    def get_model_perms(self, request):
        return {}
