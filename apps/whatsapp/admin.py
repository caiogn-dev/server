"""WhatsApp admin - LEGACY (específico do WhatsApp).

Use messaging_v2 para a versão unificada (WhatsApp, Messenger, etc).
"""
from django.contrib import admin
from .models import WhatsAppAccount, Message, MessageTemplate


@admin.register(WhatsAppAccount)
class WhatsAppAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'status', 'is_active']
    list_filter = ['status', 'is_active']
    search_fields = ['name', 'phone_number']

    def get_model_perms(self, request):
        """Não mostrar no índice do admin."""
        return {}


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['direction', 'status', 'created_at']

    def get_model_perms(self, request):
        return {}


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'language', 'status']

    def get_model_perms(self, request):
        return {}
