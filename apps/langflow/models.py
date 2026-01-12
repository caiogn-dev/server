"""
Langflow models - LLM flow management.
"""
from django.db import models
from apps.core.models import BaseModel


class LangflowFlow(BaseModel):
    """Langflow flow configuration."""
    
    class FlowStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        TESTING = 'testing', 'Testing'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    flow_id = models.CharField(max_length=100, unique=True, db_index=True)
    endpoint_url = models.URLField(blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=FlowStatus.choices,
        default=FlowStatus.INACTIVE
    )
    
    input_type = models.CharField(max_length=50, default='chat')
    output_type = models.CharField(max_length=50, default='chat')
    
    tweaks = models.JSONField(default=dict, blank=True)
    default_context = models.JSONField(default=dict, blank=True)
    
    timeout_seconds = models.PositiveIntegerField(default=30)
    max_retries = models.PositiveIntegerField(default=3)
    
    accounts = models.ManyToManyField(
        'whatsapp.WhatsAppAccount',
        related_name='langflow_flows',
        blank=True
    )

    class Meta:
        db_table = 'langflow_flows'
        verbose_name = 'Langflow Flow'
        verbose_name_plural = 'Langflow Flows'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.status})"


class LangflowSession(BaseModel):
    """Langflow session for conversation context."""
    
    flow = models.ForeignKey(
        LangflowFlow,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='langflow_sessions',
        null=True,
        blank=True
    )
    
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    context = models.JSONField(default=dict, blank=True)
    history = models.JSONField(default=list, blank=True)
    
    last_interaction_at = models.DateTimeField(auto_now=True)
    interaction_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'langflow_sessions'
        verbose_name = 'Langflow Session'
        verbose_name_plural = 'Langflow Sessions'
        ordering = ['-last_interaction_at']

    def __str__(self):
        return f"Session {self.session_id} for {self.flow.name}"

    def add_to_history(self, role: str, content: str):
        """Add message to history."""
        self.history.append({
            'role': role,
            'content': content
        })
        self.interaction_count += 1
        self.save(update_fields=['history', 'interaction_count', 'last_interaction_at'])


class LangflowLog(BaseModel):
    """Log of Langflow interactions."""
    
    class LogStatus(models.TextChoices):
        SUCCESS = 'success', 'Success'
        ERROR = 'error', 'Error'
        TIMEOUT = 'timeout', 'Timeout'

    flow = models.ForeignKey(
        LangflowFlow,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    session = models.ForeignKey(
        LangflowSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )
    
    input_message = models.TextField()
    output_message = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=LogStatus.choices)
    
    request_payload = models.JSONField(default=dict)
    response_payload = models.JSONField(default=dict)
    
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'langflow_logs'
        verbose_name = 'Langflow Log'
        verbose_name_plural = 'Langflow Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['flow', 'status', '-created_at']),
        ]

    def __str__(self):
        return f"Log {self.id} - {self.flow.name} ({self.status})"
