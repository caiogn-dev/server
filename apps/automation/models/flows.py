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

    flow_json = models.JSONField(
        default=dict,
        help_text='Estrutura do React Flow: {nodes: [], edges: []}'
    )

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Se verdadeiro, é o fluxo padrão da loja'
    )
    version = models.CharField(max_length=10, default='1.0')

    total_executions = models.PositiveIntegerField(default=0)
    success_rate = models.FloatField(default=0.0)

    class Meta:
        app_label = 'automation'
        db_table = 'agent_flows'
        ordering = ['-is_default', '-created_at']
        verbose_name = 'Fluxo de Atendimento'
        verbose_name_plural = 'Fluxos de Atendimento'

    def __str__(self):
        return f'{self.name} ({self.store.name})'

    def set_as_default(self):
        """Define este fluxo como padrão para a loja."""
        AgentFlow.objects.filter(
            store=self.store,
            is_default=True
        ).exclude(id=self.id).update(is_default=False)

        self.is_default = True
        self.save()


class FlowSession(BaseModel):
    """
    Estado da sessão de um usuário em um fluxo.
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

    current_node_id = models.CharField(max_length=100, null=True, blank=True)
    context = models.JSONField(default=dict, help_text='Variáveis coletadas durante o fluxo')
    node_history = models.JSONField(default=list, help_text='Lista de nós visitados')

    is_waiting_input = models.BooleanField(default=False)
    input_type_expected = models.CharField(max_length=50, blank=True)

    last_interaction = models.DateTimeField(auto_now=True)
    is_expired = models.BooleanField(default=False)

    class Meta:
        app_label = 'automation'
        db_table = 'flow_sessions'
        verbose_name = 'Sessão de Fluxo'
        verbose_name_plural = 'Sessões de Fluxo'

    def __str__(self):
        return f'Sessão {self.conversation.phone_number} em {self.flow.name}'

    def update_context(self, key: str, value) -> None:
        """Atualiza uma variavel no contexto do fluxo de forma atomica."""
        self.refresh_from_db(fields=['context'])
        updated = dict(self.context or {})
        updated[key] = value
        FlowSession.objects.filter(pk=self.pk).update(context=updated)
        self.context = updated

    def reset(self):
        """Reseta a sessão para o início do fluxo."""
        self.current_node_id = None
        self.context = {}
        self.node_history = []
        self.is_waiting_input = False
        self.input_type_expected = ''
        self.save()


class FlowExecutionLog(BaseModel):
    """
    Log de execução para debug e analytics.
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
    node_id = models.CharField(max_length=100)
    node_type = models.CharField(max_length=50)

    input_message = models.TextField(blank=True)
    output_message = models.TextField(blank=True)
    context_snapshot = models.JSONField(default=dict)

    execution_time_ms = models.PositiveIntegerField(default=0)
    tokens_used = models.PositiveIntegerField(default=0)

    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        app_label = 'automation'
        db_table = 'flow_execution_logs'
        ordering = ['-created_at']
        verbose_name = 'Log de Execução'
        verbose_name_plural = 'Logs de Execução'

    def __str__(self):
        status = '✅' if self.success else '❌'
        return f'{status} {self.flow.name} / {self.node_id} ({self.created_at})'
