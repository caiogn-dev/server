"""Conversations admin - LEGACY (WhatsApp específico).

Use messaging_v2 para a versão unificada.
"""
from django.contrib import admin
from .models import Conversation, ConversationNote


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'contact_name', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['phone_number', 'contact_name']

    def get_model_perms(self, request):
        """Não mostrar no índice do admin."""
        return {}


@admin.register(ConversationNote)
class ConversationNoteAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'author', 'created_at']

    def get_model_perms(self, request):
        return {}
