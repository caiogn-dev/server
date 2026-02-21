from django.db import models
from apps.core.models import BaseModel


class AgentFlow(BaseModel):
    """
    Fluxo de conversação visual (Flow Builder).
    Versão POC: Salva JSON do React Flow.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='flows')
    
    # JSON vindo do React Flow (nodes, edges, viewport)
    flow_json = models.JSONField(
        default=dict,
        help_text='Estrutura do React Flow: {nodes: [], edges: []}'
    )
    
    # Metadados
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Se verdadeiro, é o fluxo padrão da loja'
    )
    version = models.CharField(max_length=10, default='1.0')
    
    # Estatísticas
    total_executions = models.PositiveIntegerField(default=0)
    success_rate = models.FloatField(default=0.0)
    
    class Meta:
        db_table = 'agent_flows'
        ordering = ['-is_default', '-created_at']
        verbose_name = 'Fluxo de Atendimento'
        verbose_name_plural = 'Fluxos de Atendimento'
    
    def __str__(self):
        return f'{self.name} ({self.store.name})'
    
    def set_as_default(self):
        """Define este fluxo como padrão para a loja."""
        # Desativa outros defaults
        AgentFlow.objects.filter(
            store=self.store,
            is_default=True
        ).exclude(id=self.id).update(is_default=False)
        
        self.is_default = True
        self.save()


class FlowSession(BaseModel):
    """
    Estado da sessão de um usuário em um fluxo.
    Rastreia em qual nó o usuário está e o contexto acumulado.
    """
    conversation = models.OneToOneField(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='flow_session'
    )
    flow = models.ForeignKey(
        AgentFlow,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    
    # Rastreamento do fluxo
    current_node_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='ID do nó atual no React Flow'
    )
    
    # Contexto acumulado durante a conversa
    # Ex: {product_id: 123, quantity: 2, customer_name: 'João'}
    context = models.JSONField(
        default=dict,
        help_text='Variáveis coletadas durante o fluxo'
    )
    
    # Histórico de navegação
    node_history = models.JSONField(
        default=list,
        help_text='Lista de nós visitados: [node_id_1, node_id_2, ...]'
    )
    
    # Flags de estado
    is_waiting_input = models.BooleanField(
        default=False,
        help_text='Se verdadeiro, está esperando input do usuário'
    )
    input_type_expected = models.CharField(
        max_length=50,
        blank=True,
        help_text='Tipo de input esperado (text, number, email, etc)'
    )
    
    # Controle de expiração
    last_interaction = models.DateTimeField(auto_now=True)
    is_expired = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'flow_sessions'
        verbose_name = 'Sessão de Fluxo'
        verbose_name_plural = 'Sessões de Fluxo'
    
    def __str__(self):
        return f'Sessão {self.conversation.phone_number} em {self.flow.name}'
    
    def reset(self):
        """Reseta a sessão para o início do fluxo."""
        self.current_node_id = None
        self.context = {}
        self.node_history = []
        self.is_waiting_input = False
        self.input_type_expected = ''
        self.save()
    
    def update_context(self, key: str, value):
        """Atualiza uma variável no contexto."""
        self.context[key] = value
        self.save()
    
    def get_context(self, key: str, default=None):
        """Pega uma variável do contexto."""
        return self.context.get(key, default)


class FlowExecutionLog(BaseModel):
    """
    Log de execução para debug e analytics.
    Cada interação é registrada para análise posterior.
    """
    session = models.ForeignKey(
        FlowSession,
        on_delete=models.CASCADE,
        related_name='execution_logs'
    )
    flow = models.ForeignKey(
        AgentFlow,
        on_delete=models.CASCADE,
        related_name='execution_logs'
    )
    node_id = models.CharField(
        max_length=100,
        help_text='ID do nó que foi executado'
    )
    node_type = models.CharField(
        max_length=50,
        help_text='Tipo do nó (message, input, action, etc)'
    )
    
    # Dados da interação
    input_message = models.TextField(
        blank=True,
        help_text='Mensagem recebida do usuário'
    )
    output_message = models.TextField(
        blank=True,
        help_text='Mensagem enviada ao usuário'
    )
    context_snapshot = models.JSONField(
        default=dict,
        help_text='Snapshot do contexto após execução'
    )
    
    # Métricas
    execution_time_ms = models.PositiveIntegerField(
        default=0,
        help_text='Tempo de execução em milissegundos'
    )
    tokens_used = models.PositiveIntegerField(
        default=0,
        help_text='Tokens utilizados (se usar LLM)'
    )
    
    # Resultado
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'flow_execution_logs'
        ordering = ['-created_at']
        verbose_name = 'Log de Execução'
        verbose_name_plural = 'Logs de Execução'
    
    def __str__(self):
        status = '✅' if self.success else '❌'
        return f'{status} {self.node_type} em {self.flow.name}'
