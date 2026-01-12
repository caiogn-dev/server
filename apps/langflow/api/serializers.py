"""
Langflow API serializers.
"""
from rest_framework import serializers
from ..models import LangflowFlow, LangflowSession, LangflowLog


class LangflowFlowSerializer(serializers.ModelSerializer):
    """Serializer for Langflow Flow."""
    account_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LangflowFlow
        fields = [
            'id', 'name', 'description', 'flow_id', 'endpoint_url',
            'status', 'input_type', 'output_type', 'tweaks',
            'default_context', 'timeout_seconds', 'max_retries',
            'account_count', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_account_count(self, obj):
        return obj.accounts.count()


class LangflowFlowCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Langflow Flow."""
    
    class Meta:
        model = LangflowFlow
        fields = [
            'name', 'description', 'flow_id', 'endpoint_url',
            'status', 'input_type', 'output_type', 'tweaks',
            'default_context', 'timeout_seconds', 'max_retries'
        ]


class LangflowSessionSerializer(serializers.ModelSerializer):
    """Serializer for Langflow Session."""
    flow_name = serializers.CharField(source='flow.name', read_only=True)
    
    class Meta:
        model = LangflowSession
        fields = [
            'id', 'flow', 'flow_name', 'conversation', 'session_id',
            'context', 'history', 'last_interaction_at', 'interaction_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'session_id', 'last_interaction_at', 'interaction_count',
            'created_at', 'updated_at'
        ]


class LangflowLogSerializer(serializers.ModelSerializer):
    """Serializer for Langflow Log."""
    flow_name = serializers.CharField(source='flow.name', read_only=True)
    
    class Meta:
        model = LangflowLog
        fields = [
            'id', 'flow', 'flow_name', 'session', 'input_message',
            'output_message', 'status', 'duration_ms', 'error_message',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ProcessMessageSerializer(serializers.Serializer):
    """Serializer for processing message through Langflow."""
    flow_id = serializers.UUIDField()
    message = serializers.CharField(max_length=10000)
    context = serializers.DictField(required=False, default=dict)
    session_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class ProcessMessageResponseSerializer(serializers.Serializer):
    """Serializer for process message response."""
    response = serializers.CharField(allow_null=True)
    session_id = serializers.CharField()
    flow_id = serializers.CharField()


class UpdateContextSerializer(serializers.Serializer):
    """Serializer for updating session context."""
    context = serializers.DictField()


class AssignFlowSerializer(serializers.Serializer):
    """Serializer for assigning flow to accounts."""
    account_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1
    )
