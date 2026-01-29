"""
Campaign and scheduled message models.
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.whatsapp.models import WhatsAppAccount, MessageTemplate

User = get_user_model()


class Campaign(models.Model):
    """Marketing campaign model."""
    
    class CampaignStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SCHEDULED = 'scheduled', 'Scheduled'
        RUNNING = 'running', 'Running'
        PAUSED = 'paused', 'Paused'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    class CampaignType(models.TextChoices):
        BROADCAST = 'broadcast', 'Broadcast'
        DRIP = 'drip', 'Drip Campaign'
        TRIGGERED = 'triggered', 'Triggered'
        PROMOTIONAL = 'promotional', 'Promotional'
        TRANSACTIONAL = 'transactional', 'Transactional'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='campaigns'
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    campaign_type = models.CharField(
        max_length=20,
        choices=CampaignType.choices,
        default=CampaignType.BROADCAST
    )
    status = models.CharField(
        max_length=20,
        choices=CampaignStatus.choices,
        default=CampaignStatus.DRAFT
    )
    
    # Template
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns'
    )
    message_content = models.JSONField(default=dict, blank=True)
    
    # Audience
    audience_type = models.CharField(max_length=50, default='all')
    audience_filters = models.JSONField(default=dict, blank=True)
    contact_list = models.JSONField(default=list, blank=True)
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Rate limiting
    messages_per_minute = models.IntegerField(default=60)
    delay_between_messages = models.IntegerField(default=1)  # seconds
    
    # Statistics
    total_recipients = models.IntegerField(default=0)
    messages_sent = models.IntegerField(default=0)
    messages_delivered = models.IntegerField(default=0)
    messages_read = models.IntegerField(default=0)
    messages_failed = models.IntegerField(default=0)
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_campaigns'
    )
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['scheduled_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    @property
    def delivery_rate(self) -> float:
        if self.messages_sent == 0:
            return 0
        return (self.messages_delivered / self.messages_sent) * 100
    
    @property
    def read_rate(self) -> float:
        if self.messages_delivered == 0:
            return 0
        return (self.messages_read / self.messages_delivered) * 100


class CampaignRecipient(models.Model):
    """Campaign recipient tracking."""
    
    class RecipientStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='recipients'
    )
    
    phone_number = models.CharField(max_length=20)
    contact_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=RecipientStatus.choices,
        default=RecipientStatus.PENDING
    )
    
    # Message tracking
    message_id = models.CharField(max_length=100, blank=True)
    whatsapp_message_id = models.CharField(max_length=100, blank=True)
    
    # Timing
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    # Personalization
    variables = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['campaign', 'phone_number']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['phone_number']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} - {self.status}"


# NOTE: ScheduledMessage model has been moved to apps.automation.models
# Import it from there: from apps.automation.models import ScheduledMessage


class ContactList(models.Model):
    """Contact list for campaigns."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='contact_lists'
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Contacts
    contacts = models.JSONField(default=list)  # List of {phone, name, variables}
    contact_count = models.IntegerField(default=0)
    
    # Import info
    source = models.CharField(max_length=50, blank=True)  # csv, manual, api
    imported_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='contact_lists'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.contact_count} contacts)"
