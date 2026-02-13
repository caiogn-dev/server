"""
Audit API serializers.
"""
from rest_framework import serializers
from ..models import AuditLog, DataExportLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AuditLog model."""
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user_email', 'user_ip', 'action', 'action_description',
            'object_repr', 'old_values', 'new_values', 'changes',
            'module', 'extra_data', 'request_path', 'request_method',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class DataExportLogSerializer(serializers.ModelSerializer):
    """Serializer for DataExportLog model."""
    
    class Meta:
        model = DataExportLog
        fields = [
            'id', 'export_type', 'export_format', 'status', 'filters',
            'total_records', 'file_size', 'download_url',
            'started_at', 'completed_at', 'expires_at', 'error_message',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ExportRequestSerializer(serializers.Serializer):
    """Serializer for export requests."""
    export_type = serializers.ChoiceField(
        choices=['messages', 'orders', 'conversations']
    )
    export_format = serializers.ChoiceField(
        choices=['csv', 'excel'],
        default='csv'
    )
    filters = serializers.DictField(required=False, default=dict)
