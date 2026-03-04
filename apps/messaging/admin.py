"""Messaging admin - LEGACY (Messenger específico).

Use messaging_v2 para a versão unificada (WhatsApp, Messenger, etc).
"""
from django.contrib import admin
from .models import MessengerAccount, MessengerConversation, MessengerMessage


@admin.register(MessengerAccount)
class MessengerAccountAdmin(admin.ModelAdmin):
    list_display = ['page_name', 'user', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['page_name']

    def get_model_perms(self, request):
        """Não mostrar no índice do admin."""
        return {}


@admin.register(MessengerConversation)
class MessengerConversationAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'account', 'is_active']

    def get_model_perms(self, request):
        return {}


@admin.register(MessengerMessage)
class MessengerMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'message_type', 'created_at']

    def get_model_perms(self, request):
        return {}
