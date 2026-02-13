"""
Messenger models - Facebook Messenger Platform integration.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class MessengerAccount(BaseModel):
    """Facebook Page connected to Messenger."""
    
    class AccountStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        PENDING = 'pending', 'Pending Verification'
    
    name = models.CharField(max_length=255)
    page_id = models.CharField(max_length=50, unique=True, db_index=True)
    page_name = models.CharField(max_length=255)
    page_access_token = models.TextField()
    
    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING
    )
    
    webhook_verified = models.BooleanField(default=False)
    
    # AI Agent
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messenger_accounts'
    )
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)
    
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='messenger_accounts',
        null=True,
        blank=True
    )
    
    class Meta:
        db_table = 'messenger_accounts'
        verbose_name = 'Messenger Account'
        verbose_name_plural = 'Messenger Accounts'
    
    def __str__(self):
        return f"{self.name} ({self.page_name})"


class MessengerConversation(BaseModel):
    """Messenger conversation with a user."""
    
    class ConversationStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CLOSED = 'closed', 'Closed'
        ARCHIVED = 'archived', 'Archived'
    
    account = models.ForeignKey(
        MessengerAccount,
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    sender_id = models.CharField(max_length=50, db_index=True)
    sender_name = models.CharField(max_length=255)
    
    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE
    )
    
    last_message = models.TextField(blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    unread_count = models.PositiveIntegerField(default=0)
    
    # Handover
    is_bot_active = models.BooleanField(default=True)
    handover_status = models.CharField(
        max_length=20,
        default='bot',
        help_text='bot, human, or pending'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messenger_conversations'
    )
    
    class Meta:
        db_table = 'messenger_conversations'
        unique_together = ['account', 'sender_id']
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Conversation with {self.sender_name}"


class MessengerMessage(BaseModel):
    """Message in a Messenger conversation."""
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        FILE = 'file', 'File'
        TEMPLATE = 'template', 'Template'
    
    conversation = models.ForeignKey(
        MessengerConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender_id = models.CharField(max_length=50)
    sender_name = models.CharField(max_length=255)
    
    content = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT
    )
    
    # Media
    media_url = models.URLField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    
    # Status
    is_from_bot = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    
    # Metadata
    mid = models.CharField(max_length=100, blank=True, db_index=True)
    
    class Meta:
        db_table = 'messenger_messages'
        ordering = ['created_at']
    
    def __str__(self):
        return f"Message from {self.sender_name}"


class MessengerBroadcast(BaseModel):
    """Broadcast message to multiple recipients."""
    
    class BroadcastStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SCHEDULED = 'scheduled', 'Scheduled'
        SENDING = 'sending', 'Sending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
    
    account = models.ForeignKey(
        MessengerAccount,
        on_delete=models.CASCADE,
        related_name='broadcasts'
    )
    name = models.CharField(max_length=255)
    content = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=MessengerMessage.MessageType.choices,
        default=MessengerMessage.MessageType.TEXT
    )
    
    status = models.CharField(
        max_length=20,
        choices=BroadcastStatus.choices,
        default=BroadcastStatus.DRAFT
    )
    
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Stats
    recipient_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'messenger_broadcasts'
        ordering = ['-created_at']


class MessengerSponsoredMessage(BaseModel):
    """Sponsored message (paid ad)."""
    
    class AdStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        COMPLETED = 'completed', 'Completed'
    
    account = models.ForeignKey(
        MessengerAccount,
        on_delete=models.CASCADE,
        related_name='sponsored_messages'
    )
    name = models.CharField(max_length=255)
    content = models.TextField()
    image_url = models.URLField(blank=True)
    
    cta_type = models.CharField(max_length=50, default='LEARN_MORE')
    cta_url = models.URLField(blank=True)
    
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='BRL')
    
    status = models.CharField(
        max_length=20,
        choices=AdStatus.choices,
        default=AdStatus.DRAFT
    )
    
    class Meta:
        db_table = 'messenger_sponsored_messages'
