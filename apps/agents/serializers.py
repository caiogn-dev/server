"""
Serializers for Agents API
"""
from rest_framework import serializers
from .models import Agent, AgentConversation, AgentMessage


class AgentListSerializer(serializers.ModelSerializer):
    """Serializer for listing agents."""
    
    class Meta:
        model = Agent
        fields = [
            'id', 'name', 'description', 'provider', 'model_name',
            'status', 'temperature', 'max_tokens', 'use_memory',
            'created_at', 'updated_at'
        ]


class AgentDetailSerializer(serializers.ModelSerializer):
    """Serializer for agent details."""
    accounts = serializers.SerializerMethodField()
    
    class Meta:
        model = Agent
        fields = [
            'id', 'name', 'description', 'provider', 'model_name',
            'base_url', 'temperature', 'max_tokens', 'timeout',
            'system_prompt', 'context_prompt', 'status',
            'use_memory', 'memory_ttl', 'accounts',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {}
    
    def get_accounts(self, obj):
        from apps.whatsapp.api.serializers import WhatsAppAccountSerializer
        return WhatsAppAccountSerializer(obj.accounts.all(), many=True).data


class AgentCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating agents."""
    api_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True,
        help_text='API key para o provider (nunca retornada nas respostas)'
    )

    class Meta:
        model = Agent
        fields = [
            'name', 'description', 'provider', 'model_name',
            'api_key', 'base_url', 'temperature', 'max_tokens',
            'timeout', 'system_prompt', 'context_prompt',
            'status', 'use_memory', 'memory_ttl', 'accounts'
        ]

    def create(self, validated_data):
        api_key = validated_data.pop('api_key', '')
        instance = super().create(validated_data)
        if api_key:
            instance.api_key = api_key
            instance.save(update_fields=['api_key_encrypted'])
        return instance

    def update(self, instance, validated_data):
        api_key = validated_data.pop('api_key', None)
        instance = super().update(instance, validated_data)
        if api_key is not None:
            instance.api_key = api_key
            instance.save(update_fields=['api_key_encrypted'])
        return instance


class AgentMessageSerializer(serializers.ModelSerializer):
    """Serializer for agent messages."""
    
    class Meta:
        model = AgentMessage
        fields = ['id', 'role', 'content', 'tokens_used', 'created_at']


class AgentConversationSerializer(serializers.ModelSerializer):
    """Serializer for agent conversations."""
    messages = AgentMessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = AgentConversation
        fields = [
            'id', 'session_id', 'phone_number', 'message_count',
            'last_message_at', 'messages', 'created_at'
        ]


class ProcessMessageSerializer(serializers.Serializer):
    """Serializer for processing messages."""
    message = serializers.CharField(required=True, help_text="Mensagem do usuário")
    session_id = serializers.CharField(required=False, allow_blank=True, help_text="ID da sessão (opcional)")
    phone_number = serializers.CharField(required=False, allow_blank=True, help_text="Número de telefone")
    context = serializers.DictField(required=False, default=dict, help_text="Contexto adicional")


class ProcessMessageResponseSerializer(serializers.Serializer):
    """Serializer for process message response."""
    response = serializers.CharField()
    session_id = serializers.CharField()
    tokens_used = serializers.IntegerField(required=False)
    response_time_ms = serializers.IntegerField(required=False)


class AgentStatsSerializer(serializers.Serializer):
    """Serializer for agent statistics."""
    total_conversations = serializers.IntegerField()
    total_messages = serializers.IntegerField()
    avg_response_time_ms = serializers.FloatField()
    active_sessions = serializers.IntegerField()
