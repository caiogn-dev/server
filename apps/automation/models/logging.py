from django.db import models
from apps.core.models import BaseModel


class AutomationLog(BaseModel):
    """
    Log of all automation actions for debugging and analytics.
    """

    class ActionType(models.TextChoices):
        MESSAGE_RECEIVED = 'message_received', 'Mensagem Recebida'
        MESSAGE_SENT = 'message_sent', 'Mensagem Enviada'
        WEBHOOK_RECEIVED = 'webhook_received', 'Webhook Recebido'
        SESSION_CREATED = 'session_created', 'Sessão Criada'
        SESSION_UPDATED = 'session_updated', 'Sessão Atualizada'
        NOTIFICATION_SENT = 'notification_sent', 'Notificação Enviada'
        ERROR = 'error', 'Erro'

    company = models.ForeignKey(
        'automation.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='automation_logs'
    )
    session = models.ForeignKey(
        'automation.CustomerSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )

    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    description = models.TextField()

    phone_number = models.CharField(max_length=20, blank=True)
    event_type = models.CharField(max_length=50, blank=True)

    request_data = models.JSONField(default=dict, blank=True)
    response_data = models.JSONField(default=dict, blank=True)

    is_error = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        app_label = 'automation'
        db_table = 'automation_logs'
        verbose_name = 'Automation Log'
        verbose_name_plural = 'Automation Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.company.company_name} - {self.action_type} - {self.created_at}"


class IntentLog(BaseModel):
    """
    Log de detecção de intenções para analytics e debugging.
    """

    class MethodType(models.TextChoices):
        REGEX = 'regex', 'Regex'
        LLM = 'llm', 'LLM'
        NONE = 'none', 'Nenhum'

    class ResponseType(models.TextChoices):
        TEXT = 'text', 'Texto'
        BUTTONS = 'buttons', 'Botões'
        LIST = 'list', 'Lista'
        INTERACTIVE = 'interactive', 'Interativo'

    company = models.ForeignKey(
        'automation.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='intent_logs'
    )
    message = models.ForeignKey(
        'whatsapp.Message',
        on_delete=models.CASCADE,
        related_name='intent_logs',
        null=True,
        blank=True
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='intent_logs',
        null=True,
        blank=True
    )

    phone_number = models.CharField(max_length=20, db_index=True)
    message_text = models.TextField()

    intent_type = models.CharField(max_length=50, db_index=True)
    method = models.CharField(max_length=10, choices=MethodType.choices, default=MethodType.REGEX)
    confidence = models.FloatField(default=0.0)

    handler_used = models.CharField(max_length=100, blank=True)
    response_text = models.TextField(blank=True)
    response_type = models.CharField(
        max_length=20,
        choices=ResponseType.choices,
        default=ResponseType.TEXT
    )

    processing_time_ms = models.IntegerField(default=0)

    entities = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'automation'
        db_table = 'intent_logs'
        verbose_name = 'Intent Log'
        verbose_name_plural = 'Intent Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),
            models.Index(fields=['intent_type', '-created_at']),
            models.Index(fields=['method', '-created_at']),
            models.Index(fields=['phone_number', '-created_at']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.intent_type} ({self.method}) - {self.created_at}"
