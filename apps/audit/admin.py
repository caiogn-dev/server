from django.contrib import admin
from .models import AuditLog, DataExportLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user_email', 'action_description', 'module', 'created_at']
    list_filter = ['action', 'module', 'created_at']
    search_fields = ['user_email', 'action_description', 'object_repr']
    readonly_fields = ['id', 'created_at']
    date_hierarchy = 'created_at'


@admin.register(DataExportLog)
class DataExportLogAdmin(admin.ModelAdmin):
    list_display = ['export_type', 'user', 'export_format', 'status', 'total_records', 'created_at']
    list_filter = ['export_type', 'export_format', 'status', 'created_at']
    search_fields = ['user__username', 'export_type']
    readonly_fields = ['id', 'created_at', 'updated_at']
