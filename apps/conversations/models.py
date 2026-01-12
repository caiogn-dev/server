"""
Conversations models - Conversation management.
"""
from django.db import models
from apps.core.models import BaseModel


class Conversation(BaseModel):
    """Conversation model for tracking chat sessions."""
    
    class ConversationMode(models.TextChoices):
        AUTO = 'auto', 'Automated'
        HUMAN = 'human', 'Human Agent'
        HYBRID = 'hybrid', 'Hybrid'

    class ConversationStatus(models.TextChoices):
        OPEN = 'open', 'Open'
        CLOSED = 'closed', 'Closed'
        PENDING = 'pending', 'Pending'
        RESOLVED = 'resolved', 'Resolved'

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    
    phone_number = models.CharField(max_length=20, db_index=True)
    contact_name = models.CharField(max_length=255, blank=True)
    
    mode = models.CharField(
        max_length=10,
        choices=ConversationMode.choices,
        default=ConversationMode.AUTO
    )
    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.OPEN
    )
    
    assigned_agent = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_conversations'
    )
    
    langflow_flow_id = models.UUIDField(null=True, blank=True)
    langflow_session_id = models.CharField(max_length=100, blank=True)
    
    context = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_customer_message_at = models.DateTimeField(null=True, blank=True)
    last_agent_message_at = models.DateTimeField(null=True, blank=True)
    
    closed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'conversations'
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        ordering = ['-last_message_at', '-created_at']
        unique_together = ['account', 'phone_number']
        indexes = [
            models.Index(fields=['account', 'status', '-last_message_at']),
            models.Index(fields=['assigned_agent', 'status']),
        ]

    def __str__(self):
        return f"Conversation with {self.contact_name or self.phone_number}"


class ConversationNote(BaseModel):
    """Notes attached to conversations."""
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='notes'
    )
    author = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='conversation_notes'
    )
    content = models.TextField()
    
    class Meta:
        db_table = 'conversation_notes'
        verbose_name = 'Conversation Note'
        verbose_name_plural = 'Conversation Notes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.conversation} by {self.author}"
