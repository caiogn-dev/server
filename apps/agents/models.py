"""
Models for Langchain Agents
"""
import uuid
from django.db import models
from apps.core.models import BaseModel


class Agent(BaseModel):
    """
    AI Agent configuration using Langchain.
    Replaces Langflow flows with native Langchain implementation.
    """

    class AgentStatus(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        INACTIVE = 'inactive', 'Inativo'
        DRAFT = 'draft', 'Rascunho'

    class AgentProvider(models.TextChoices):
        KIMI = 'kimi', 'Kimi (Moonshot)'
        OPENAI = 'openai', 'OpenAI'
        ANTHROPIC = 'anthropic', 'Anthropic'
        OLLAMA = 'ollama', 'Ollama (Local)'
        NVIDIA = 'nvidia', 'NVIDIA AI'

    name = models.CharField(max_length=255, verbose_name='Nome')
    description = models.TextField(blank=True, verbose_name='Descrição')

    # Provider configuration
    provider = models.CharField(
        max_length=20,
        choices=AgentProvider.choices,
        default=AgentProvider.KIMI,
        verbose_name='Provedor'
    )
    model_name = models.CharField(
        max_length=100,
        default='kimi-coder',
        verbose_name='Modelo'
    )
    api_key = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='API Key'
    )
    base_url = models.URLField(
        blank=True,
        default='https://api.moonshot.cn/v1',
        verbose_name='Base URL'
    )

    # Model parameters
    temperature = models.FloatField(default=0.7, verbose_name='Temperature')
    max_tokens = models.PositiveIntegerField(default=1000, verbose_name='Max Tokens')
    timeout = models.PositiveIntegerField(default=30, verbose_name='Timeout (segundos)')

    # Prompt configuration
    system_prompt = models.TextField(
        default='Você é um assistente virtual útil.',
        verbose_name='System Prompt'
    )
    context_prompt = models.TextField(
        blank=True,
        verbose_name='Contexto Adicional',
        help_text='Informações adicionais sobre o negócio, cardápio, etc.'
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=AgentStatus.choices,
        default=AgentStatus.DRAFT,
        verbose_name='Status'
    )

    # Associated WhatsApp accounts
    accounts = models.ManyToManyField(
        'whatsapp.WhatsAppAccount',
        related_name='agents',
        blank=True,
        verbose_name='Contas WhatsApp'
    )

    # Redis configuration for memory
    use_memory = models.BooleanField(default=True, verbose_name='Usar Memória')
    memory_ttl = models.PositiveIntegerField(
        default=86400,  # 24 hours
        verbose_name='TTL da Memória (segundos)',
        help_text='Tempo que as conversas ficam armazenadas no Redis (padrão: 24h)'
    )
    max_context_messages = models.PositiveIntegerField(
        default=10,
        verbose_name='Máximo de mensagens de contexto',
        help_text='Número máximo de mensagens históricas para manter no contexto'
    )

    class Meta:
        db_table = 'agents'
        verbose_name = 'Agente'
        verbose_name_plural = 'Agentes'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.provider})"

    def get_full_prompt(self) -> str:
        """Returns the complete prompt with system + context."""
        if self.context_prompt:
            return f"{self.system_prompt}\n\n{self.context_prompt}"
        return self.system_prompt


class AgentConversation(BaseModel):
    """
    Stores conversation sessions with agents.
    Uses Redis for active conversations, this is for persistence/history.
    """
    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        verbose_name='Session ID'
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name='conversations',
        verbose_name='Agente'
    )
    whatsapp_conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_sessions',
        verbose_name='Conversa WhatsApp'
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name='Número de Telefone'
    )
    
    # User reference (optional)
    user_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='ID do Usuário'
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadados'
    )
    
    # Metrics
    message_count = models.PositiveIntegerField(default=0, verbose_name='Contagem de Mensagens')
    last_message_at = models.DateTimeField(auto_now=True, verbose_name='Última Mensagem')

    class Meta:
        db_table = 'agent_conversations'
        verbose_name = 'Conversa do Agente'
        verbose_name_plural = 'Conversas dos Agentes'
        ordering = ['-last_message_at']

    def __str__(self):
        return f"Sessão {self.session_id} - {self.agent.name}"


class AgentMessage(BaseModel):
    """
    Individual messages in agent conversations.
    """
    class MessageRole(models.TextChoices):
        USER = 'user', 'Usuário'
        ASSISTANT = 'assistant', 'Assistente'
        SYSTEM = 'system', 'Sistema'

    conversation = models.ForeignKey(
        AgentConversation,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Conversa'
    )
    role = models.CharField(
        max_length=20,
        choices=MessageRole.choices,
        verbose_name='Papel'
    )
    content = models.TextField(verbose_name='Conteúdo')
    tokens_used = models.PositiveIntegerField(null=True, blank=True, verbose_name='Tokens Usados')
    response_time_ms = models.PositiveIntegerField(null=True, blank=True, verbose_name='Tempo de Resposta (ms)')
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadados'
    )

    class Meta:
        db_table = 'agent_messages'
        verbose_name = 'Mensagem do Agente'
        verbose_name_plural = 'Mensagens dos Agentes'
        ordering = ['created_at']
