"""
Conversations models - Conversation management.
"""
from django.db import models
import uuid
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
    
    # AI Agent (Langchain) configuration
    ai_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_conversations',
        help_text='Agente IA vinculado a esta conversa'
    )
    agent_session_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='ID da sessão do agente para memória'
    )
    
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
# ============================================
# HANDOVER PROTOCOL - Bot ↔ Human Transfer
# ============================================

class ConversationHandover(models.Model):
    """
    Controle de transferência de conversa entre bot e atendente humano.
    """
    
    class OwnerType(models.TextChoices):
        BOT = 'bot', 'Bot (IA)'
        HUMAN = 'human', 'Atendente Humano'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        PENDING = 'pending', 'Pendente'
        COMPLETED = 'completed', 'Completo'
        EXPIRED = 'expired', 'Expirado'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='handovers',
        verbose_name='Conversação'
    )
    
    current_owner = models.CharField(
        max_length=10,
        choices=OwnerType.choices,
        default=OwnerType.BOT,
        verbose_name='Dono Atual'
    )
    
    requested_owner = models.CharField(
        max_length=10,
        choices=OwnerType.choices,
        blank=True,
        null=True,
        verbose_name='Dono Solicitado'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name='Status'
    )
    
    human_agent_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID do Atendente'
    )
    
    human_agent_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Nome do Atendente'
    )
    
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Iniciado em')
    expires_at = models.DateTimeField(verbose_name='Expira em')
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name='Finalizado em')
    reason = models.TextField(blank=True, verbose_name='Motivo')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadados')
    
    class Meta:
        db_table = 'conversation_handovers'
        verbose_name = 'Handover de Conversa'
        verbose_name_plural = 'Handovers de Conversas'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['conversation', 'status']),
            models.Index(fields=['current_owner', 'status']),
            models.Index(fields=['human_agent_id', 'status']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return "Handover %s - %s" % (self.conversation.id, self.get_current_owner_display())
    
    def is_active(self):
        return self.status == self.Status.ACTIVE
    
    def is_expired(self):
        from django.utils import timezone
        return self.expires_at and self.expires_at < timezone.now()
    
    def pass_to_human(self, agent_id, agent_name=None, duration_minutes=30):
        from django.utils import timezone
        self.current_owner = self.OwnerType.HUMAN
        self.human_agent_id = agent_id
        self.human_agent_name = agent_name or agent_id
        self.expires_at = timezone.now() + timezone.timedelta(minutes=duration_minutes)
        self.status = self.Status.ACTIVE
        self.save()
    
    def return_to_bot(self):
        from django.utils import timezone
        self.current_owner = self.OwnerType.BOT
        self.status = self.Status.COMPLETED
        self.ended_at = timezone.now()
        self.save()
    
    def extend_expiration(self, minutes=30):
        from django.utils import timezone
        self.expires_at = timezone.now() + timezone.timedelta(minutes=minutes)
        self.save()
