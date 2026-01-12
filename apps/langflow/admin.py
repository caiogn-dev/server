"""
Langflow admin configuration.
"""
from django.contrib import admin
from .models import LangflowFlow, LangflowSession, LangflowLog


@admin.register(LangflowFlow)
class LangflowFlowAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'flow_id', 'status', 'input_type', 'output_type',
        'timeout_seconds', 'created_at', 'is_active'
    ]
    list_filter = ['status', 'is_active']
    search_fields = ['name', 'flow_id', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    filter_horizontal = ['accounts']


@admin.register(LangflowSession)
class LangflowSessionAdmin(admin.ModelAdmin):
    list_display = [
        'session_id', 'flow', 'conversation', 'interaction_count',
        'last_interaction_at', 'created_at'
    ]
    list_filter = ['flow']
    search_fields = ['session_id']
    readonly_fields = ['id', 'session_id', 'created_at', 'updated_at']
    raw_id_fields = ['flow', 'conversation']


@admin.register(LangflowLog)
class LangflowLogAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'flow', 'session', 'status', 'duration_ms', 'created_at'
    ]
    list_filter = ['status', 'flow']
    search_fields = ['input_message', 'output_message']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['flow', 'session']
