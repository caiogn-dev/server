"""
Unified Message model.

Replaces:
- whatsapp.Message
- messaging.MessengerMessage
- instagram.InstagramMessage
- messaging_v2.UnifiedMessage
"""

import uuid
from django.db import models
from apps.core.models import BaseModel


class UnifiedMessage(BaseModel):
    """
    Unified message model for all messaging platforms.
    
    Stores all messages from WhatsApp, Instagram, and Messenger in a single table.
    """
    
    class PlatformType(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        DOCUMENT = 'document', 'Document'
        STICKER = 'sticker', 'Sticker'
        LOCATION = 'location', 'Location'
        CONTACT = 'contact', 'Contact'
        TEMPLATE = 'template', 'Template'
        INTERACTIVE = 'interactive', 'Interactive'
        BUTTON = 'button', 'Button'
        REACTION = 'reaction', 'Reaction'
        ORDER = 'order', 'Order'
        SYSTEM = 'system', 'System'
        UNKNOWN = 'unknown', 'Unknown'
    
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    conversation = models.ForeignKey(
        'messaging.UnifiedConversation',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    platform_account = models.ForeignKey(
        'messaging.PlatformAccount',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    # Platform identification
    platform = models.CharField(
        max_length=20,
        choices=PlatformType.choices,
        db_index=True
    )
    
    # Direction and type
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        db_index=True
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT
    )
    
    # Content
    text_body = models.TextField(blank=True)
    content = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured content data'
    )
    
    # Media
    media_url = models.URLField(blank=True)
    media_mime_type = models.CharField(max_length=100, blank=True)
    media_sha256 = models.CharField(max_length=64, blank=True)
    media_caption = models.TextField(blank=True)
    
    # Template (for WhatsApp templates)
    template_name = models.CharField(max_length=255, blank=True)
    template_language = models.CharField(max_length=10, blank=True)
    template_components = models.JSONField(default=list, blank=True)
    
    # External IDs (platform-specific message IDs)
    external_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text='Platform-specific message ID'
    )
    
    # Context (for replies and forwards)
    context_message_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='ID of message being replied to'
    )
    is_forwarded = models.BooleanField(default=False)
    forwarded_count = models.PositiveIntegerField(default=0)
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Timestamps
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    # AI/Automation tracking
    processed_by_agent = models.BooleanField(
        default=False,
        help_text='Message was processed by AI agent'
    )
    agent_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='ID of agent that processed this message'
    )
    
    # Source tracking
    source = models.CharField(
        max_length=50,
        default='manual',
        help_text='Source: manual, automation, campaign, api, webhook'
    )
    campaign_id = models.UUIDField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Raw webhook data (for debugging)
    raw_webhook_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Raw data from platform webhook'
    )
    
    class Meta:
        db_table = 'unified_messages'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['platform_account', 'direction', '-created_at']),
            models.Index(fields=['external_id', 'platform']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['direction', 'status']),
            models.Index(fields=['platform', 'message_type']),
            models.Index(fields=['processed_by_agent']),
        ]
    
    def __str__(self):
        preview = self.text_body[:50] if self.text_body else f'({self.message_type})'
        return f"{self.direction}: {preview}"
    
    def mark_sent(self, external_id: str = None):
        """Mark message as sent."""
        self.status = self.Status.SENT
        self.sent_at = __import__('django.utils.timezone').now()
        if external_id:
            self.external_id = external_id
        self.save(update_fields=['status', 'sent_at', 'external_id', 'updated_at'])
    
    def mark_delivered(self):
        """Mark message as delivered."""
        self.status = self.Status.DELIVERED
        self.delivered_at = __import__('django.utils.timezone').now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])
    
    def mark_read(self):
        """Mark message as read."""
        self.status = self.Status.READ
        self.read_at = __import__('django.utils.timezone').now()
        self.save(update_fields=['status', 'read_at', 'updated_at'])
    
    def mark_failed(self, error_code: str = None, error_message: str = None):
        """Mark message as failed."""
        self.status = self.Status.FAILED
        self.failed_at = __import__('django.utils.timezone').now()
        if error_code:
            self.error_code = error_code
        if error_message:
            self.error_message = error_message
        self.save(update_fields=['status', 'failed_at', 'error_code', 'error_message', 'updated_at'])
    
    def mark_processed_by_agent(self, agent_id: str = None):
        """Mark message as processed by AI agent."""
        self.processed_by_agent = True
        if agent_id:
            self.agent_id = agent_id
        self.save(update_fields=['processed_by_agent', 'agent_id', 'updated_at'])
    
    @property
    def is_inbound(self) -> bool:
        return self.direction == self.Direction.INBOUND
    
    @property
    def is_outbound(self) -> bool:
        return self.direction == self.Direction.OUTBOUND
    
    @property
    def preview(self) -> str:
        """Get message preview for display."""
        if self.text_body:
            return self.text_body[:100]
        if self.media_caption:
            return self.media_caption[:100]
        return f"({self.get_message_type_display()})"
