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
        extra_kwargs = {
            'api_key': {'write_only': True},  # Hide API key in responses
        }
    
    def get_accounts(self, obj):
        from apps.whatsapp.api.serializers import WhatsAppAccountSerializer
        return WhatsAppAccountSerializer(obj.accounts.all(), many=True).data


class AgentCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating agents.

    Responde com o MESMO contrato da leitura (AgentDetailSerializer). Sem isso,
    o painel recebia um objeto sem `id` e com `accounts` em PKs: `agent.id`
    virava undefined (o botão de salvar voltava a dizer "Criar Agente") e o
    save seguinte mandava `accounts: [null]`, que o DRF rejeitava com
    "Pk inválido \"None\"".
    """

    class Meta:
        model = Agent
        fields = [
            'name', 'description', 'provider', 'model_name',
            'api_key', 'base_url', 'temperature', 'max_tokens',
            'timeout', 'system_prompt', 'context_prompt',
            'status', 'use_memory', 'memory_ttl', 'accounts'
        ]

    def to_internal_value(self, data):
        # Front antigo em cache continua mandando [null]; descartar um nulo é
        # mais honesto que devolver 400 para um campo que nem é obrigatório.
        accounts = data.get('accounts') if hasattr(data, 'get') else None
        if isinstance(accounts, list) and any(a in (None, '') for a in accounts):
            data = data.copy()
            data['accounts'] = [a for a in accounts if a not in (None, '')]
        return super().to_internal_value(data)

    def to_representation(self, instance):
        return AgentDetailSerializer(instance, context=self.context).data


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
    message = serializers.CharField(required=True, max_length=10000, help_text="Mensagem do usuário")
    session_id = serializers.CharField(required=False, allow_blank=True, help_text="ID da sessão (opcional)")
    phone_number = serializers.CharField(required=False, allow_blank=True, help_text="Número de telefone")
    # Sem a loja, `buscar_produto` devolve "Cardápio indisponível no momento" e
    # quem testa conclui que o catálogo quebrou. O Agent é global (não tem
    # vínculo com loja), então ela precisa vir na requisição — é o mesmo que
    # acontece no WhatsApp, onde vem da conversa.
    store = serializers.CharField(required=False, allow_blank=True, help_text="Slug ou id da loja")
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
