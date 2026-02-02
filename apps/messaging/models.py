"""
Messaging models - Unified message tracking across all channels.
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel

User = get_user_model()


class Message(BaseModel):
    """
    Unified message model for all communication channels.
    Tracks messages sent via WhatsApp, Instagram, Email, etc.
    """
    
    class Channel(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
        PUSH = 'push', 'Push Notification'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        QUEUED = 'queued', 'Queued'
        SENDING = 'sending', 'Sending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    class Priority(models.IntegerChoices):
        LOW = 1, 'Low'
        NORMAL = 5, 'Normal'
        HIGH = 10, 'High'
        URGENT = 20, 'Urgent'
    
    # Store context
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='messages',
        null=True,
        blank=True
    )
    
    # Channel and recipient
    channel = models.CharField(max_length=20, choices=Channel.choices)
    recipient = models.CharField(max_length=255, db_index=True, help_text="Phone, email, or user ID")
    recipient_name = models.CharField(max_length=255, blank=True)
    
    # Content
    message_type = models.CharField(max_length=20, default='text')
    content = models.JSONField(default=dict, help_text="Message content (text, media, etc.)")
    text = models.TextField(blank=True, help_text="Plain text content for search")
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    priority = models.IntegerField(choices=Priority.choices, default=Priority.NORMAL)
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    # External tracking
    external_id = models.CharField(max_length=255, blank=True, help_text="ID from provider (WhatsApp message ID, etc.)")
    external_status = models.CharField(max_length=50, blank=True)
    
    # Template reference
    template = models.ForeignKey(
        'MessageTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages'
    )
    
    # Source tracking
    source = models.CharField(
        max_length=30,
        default='api',
        help_text="Source: api, automation, campaign, webhook, manual"
    )
    source_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID of the source object (campaign ID, automation ID, etc.)"
    )
    
    # Error tracking
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    
    # Context
    metadata = models.JSONField(default=dict, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_messages'
    )

    class Meta:
        db_table = 'messaging_messages'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'channel', 'status']),
            models.Index(fields=['store', 'recipient', '-created_at']),
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['source', 'source_id']),
            models.Index(fields=['external_id']),
        ]

    def __str__(self):
        return f"{self.channel}: {self.recipient} ({self.status})"
    
    def mark_sent(self, external_id: str = None):
        """Mark message as sent."""
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        if external_id:
            self.external_id = external_id
        self.save(update_fields=['status', 'sent_at', 'external_id', 'updated_at'])
    
    def mark_delivered(self):
        """Mark message as delivered."""
        self.status = self.Status.DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])
    
    def mark_read(self):
        """Mark message as read."""
        self.status = self.Status.READ
        self.read_at = timezone.now()
        self.save(update_fields=['status', 'read_at', 'updated_at'])
    
    def mark_failed(self, error_code: str = None, error_message: str = None):
        """Mark message as failed."""
        self.status = self.Status.FAILED
        self.failed_at = timezone.now()
        if error_code:
            self.error_code = error_code
        if error_message:
            self.error_message = error_message
        self.save(update_fields=['status', 'failed_at', 'error_code', 'error_message', 'updated_at'])
    
    def can_retry(self) -> bool:
        """Check if message can be retried."""
        return self.retry_count < self.max_retries and self.status == self.Status.FAILED


class MessageTemplate(BaseModel):
    """
    Unified message templates that work across all channels.
    """
    
    class Channel(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
        UNIVERSAL = 'universal', 'Universal'
    
    class TemplateStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        ARCHIVED = 'archived', 'Archived'
    
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='message_templates',
        null=True,
        blank=True
    )
    
    name = models.CharField(max_length=255)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.UNIVERSAL)
    
    # Content
    subject = models.CharField(max_length=255, blank=True, help_text="Subject for email")
    body = models.TextField(help_text="Template body with {variable} placeholders")
    html_body = models.TextField(blank=True, help_text="HTML version for email")
    
    # Media
    media_url = models.URLField(blank=True)
    media_type = models.CharField(max_length=20, blank=True)
    
    # Interactive elements
    buttons = models.JSONField(default=list, blank=True)
    
    # Variables definition
    variables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of required variables: [{'name': 'customer_name', 'type': 'string', 'required': true}]"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=TemplateStatus.choices,
        default=TemplateStatus.DRAFT
    )
    
    # WhatsApp specific
    whatsapp_template_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the approved template in WhatsApp Business API"
    )
    whatsapp_template_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="APPROVED, REJECTED, PENDING"
    )
    
    # Usage stats
    usage_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    # Category
    category = models.CharField(max_length=50, blank=True, help_text="Marketing, Utility, Authentication")
    language = models.CharField(max_length=10, default='pt_BR')
    
    class Meta:
        db_table = 'messaging_templates'
        verbose_name = 'Message Template'
        verbose_name_plural = 'Message Templates'
        ordering = ['store', 'name']
        unique_together = ['store', 'name', 'channel']

    def __str__(self):
        return f"{self.name} ({self.channel})"
    
    def render(self, variables: dict) -> dict:
        """Render template with variables."""
        import re
        
        result = {
            'subject': self.subject,
            'body': self.body,
            'html_body': self.html_body,
        }
        
        for key, value in variables.items():
            placeholder = f'{{{key}}}'
            for field in ['subject', 'body', 'html_body']:
                if result[field]:
                    result[field] = result[field].replace(placeholder, str(value))
        
        return result
    
    def record_usage(self):
        """Record template usage."""
        self.usage_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at'])


class MessageRule(BaseModel):
    """
    Global messaging rules (rate limiting, quiet hours, etc.)
    """
    
    class RuleType(models.TextChoices):
        QUIET_HOURS = 'quiet_hours', 'Quiet Hours'
        RATE_LIMIT = 'rate_limit', 'Rate Limit'
        BLACKLIST = 'blacklist', 'Blacklist'
        WHITELIST = 'whitelist', 'Whitelist'
        MAX_DAILY = 'max_daily', 'Max Daily Messages'
    
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='messaging_rules',
        null=True,
        blank=True,
        help_text="Global rules if null, store-specific if set"
    )
    
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    
    # Rule configuration
    config = models.JSONField(default=dict, help_text="Rule-specific configuration")
    
    # Channels this rule applies to
    channels = models.JSONField(
        default=list,
        help_text="List of channels: ['whatsapp', 'email', 'sms']"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=100)
    
    class Meta:
        db_table = 'messaging_rules'
        verbose_name = 'Message Rule'
        verbose_name_plural = 'Message Rules'
        ordering = ['priority', 'name']

    def __str__(self):
        scope = "Global" if not self.store else self.store.name
        return f"{self.name} ({scope})"
    
    def applies_to(self, channel: str) -> bool:
        """Check if rule applies to a channel."""
        return not self.channels or channel in self.channels


class MessageLog(BaseModel):
    """
    Detailed log of message processing for debugging.
    """
    
    class LogLevel(models.TextChoices):
        DEBUG = 'debug', 'Debug'
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'
    
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    
    level = models.CharField(max_length=10, choices=LogLevel.choices, default=LogLevel.INFO)
    action = models.CharField(max_length=50, help_text="Action being performed")
    description = models.TextField()
    
    # Data
    request_data = models.JSONField(default=dict, blank=True)
    response_data = models.JSONField(default=dict, blank=True)
    
    # Timing
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'messaging_logs'
        verbose_name = 'Message Log'
        verbose_name_plural = 'Message Logs'
        ordering = ['-created_at']
