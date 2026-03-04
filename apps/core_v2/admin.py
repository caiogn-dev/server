"""Core v2 models admin - Visão unificada.

AuditLog está em apps.audit - mantido lá para preservar dados históricos.
"""
from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """AuditLog do Core v2 - consolidado com apps.audit.
    Registro invisível para evitar duplicação no admin.
    """
    list_display = ['action', 'entity_type', 'entity_id', 'user', 'created_at']
    list_filter = ['action', 'entity_type', 'created_at']
    search_fields = ['entity_type', 'entity_id', 'description']
    readonly_fields = ['id', 'created_at', 'action', 'entity_type', 'entity_id', 'description', 'metadata']
    date_hierarchy = 'created_at'

    def get_model_perms(self, request):
        """Não mostrar no índice do admin."""
        return {}
