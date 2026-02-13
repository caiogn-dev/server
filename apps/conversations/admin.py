"""
Conversation admin configuration.
"""
from django.contrib import admin
from .models import Conversation, ConversationNote


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'account', 'phone_number', 'contact_name', 'mode',
        'status', 'assigned_agent', 'last_message_at', 'created_at'
    ]
    list_filter = ['status', 'mode', 'account', 'assigned_agent']
    search_fields = ['phone_number', 'contact_name']
    readonly_fields = [
        'id', 'last_message_at', 'last_customer_message_at',
        'last_agent_message_at', 'closed_at', 'resolved_at',
        'created_at', 'updated_at'
    ]
    raw_id_fields = ['account', 'assigned_agent']


@admin.register(ConversationNote)
class ConversationNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'author', 'created_at']
    list_filter = ['author']
    search_fields = ['content']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['conversation', 'author']
