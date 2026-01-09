"""
WhatsApp models - WhatsApp accounts, messages, and webhook events.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from apps.core.utils import token_encryption, mask_token

User = get_user_model()


class WhatsAppAccount(BaseModel):
    """WhatsApp Business Account configuration."""
    
    class AccountStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'
        PENDING = 'pending', 'Pending Verification'

    name = models.CharField(max_length=255)
    phone_number_id = models.CharField(max_length=50, unique=True, db_index=True)
    waba_id = models.CharField(max_length=50, db_index=True)
    phone_number = models.CharField(max_length=20)
    display_phone_number = models.CharField(max_length=30, blank=True)
    
    access_token_encrypted = models.TextField()
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=1)
    
    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING
    )
    
    webhook_verify_token = models.CharField(max_length=255, blank=True)
    
    default_langflow_flow_id = models.UUIDField(null=True, blank=True)
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='whatsapp_accounts',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'whatsapp_accounts'
        verbose_name = 'WhatsApp Account'
        verbose_name_plural = 'WhatsApp Accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.display_phone_number or self.phone_number})"

    @property
    def access_token(self) -> str:
        """Decrypt and return the access token."""
        return token_encryption.decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value: str):
        """Encrypt and store the access token."""
        self.access_token_encrypted = token_encryption.encrypt(value)
        self.token_version += 1

    @property
    def masked_token(self) -> str:
        """Return masked token for display."""
        return mask_token(self.access_token)

    def rotate_token(self, new_token: str):
        """Rotate the access token."""
        self.access_token = new_token
        self.save(update_fields=['access_token_encrypted', 'token_version', 'updated_at'])


class Message(BaseModel):
    """WhatsApp message model."""
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        DOCUMENT = 'document', 'Document'
        STICKER = 'sticker', 'Sticker'
        LOCATION = 'location', 'Location'
        CONTACTS = 'contacts', 'Contacts'
        INTERACTIVE = 'interactive', 'Interactive'
        TEMPLATE = 'template', 'Template'
        REACTION = 'reaction', 'Reaction'
        BUTTON = 'button', 'Button'
        ORDER = 'order', 'Order'
        SYSTEM = 'system', 'System'
        UNKNOWN = 'unknown', 'Unknown'

    class MessageDirection(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'

    class MessageStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'

    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages'
    )
    
    whatsapp_message_id = models.CharField(max_length=100, unique=True, db_index=True)
    direction = models.CharField(max_length=10, choices=MessageDirection.choices)
    message_type = models.CharField(max_length=20, choices=MessageType.choices)
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING
    )
    
    from_number = models.CharField(max_length=20, db_index=True)
    to_number = models.CharField(max_length=20, db_index=True)
    
    content = models.JSONField(default=dict)
    text_body = models.TextField(blank=True)
    
    media_id = models.CharField(max_length=100, blank=True)
    media_url = models.URLField(blank=True)
    media_mime_type = models.CharField(max_length=100, blank=True)
    media_sha256 = models.CharField(max_length=64, blank=True)
    
    template_name = models.CharField(max_length=255, blank=True)
    template_language = models.CharField(max_length=10, blank=True)
    
    context_message_id = models.CharField(max_length=100, blank=True)
    
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    processed_by_langflow = models.BooleanField(default=False)

    class Meta:
        db_table = 'whatsapp_messages'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'from_number', '-created_at']),
            models.Index(fields=['account', 'to_number', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.direction}: {self.from_number} -> {self.to_number} ({self.message_type})"


class WebhookEvent(BaseModel):
    """Webhook event log for idempotency and debugging."""
    
    class EventType(models.TextChoices):
        MESSAGE = 'message', 'Message'
        STATUS = 'status', 'Status Update'
        ERROR = 'error', 'Error'
        UNKNOWN = 'unknown', 'Unknown'

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DUPLICATE = 'duplicate', 'Duplicate'

    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='webhook_events',
        null=True,
        blank=True
    )
    
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )
    
    payload = models.JSONField()
    headers = models.JSONField(default=dict)
    
    processed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    
    related_message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )

    class Meta:
        db_table = 'whatsapp_webhook_events'
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['processing_status', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.event_id} ({self.processing_status})"


class MessageTemplate(BaseModel):
    """WhatsApp message template."""
    
    class TemplateStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class TemplateCategory(models.TextChoices):
        MARKETING = 'marketing', 'Marketing'
        UTILITY = 'utility', 'Utility'
        AUTHENTICATION = 'authentication', 'Authentication'

    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='templates'
    )
    
    template_id = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255)
    language = models.CharField(max_length=10, default='pt_BR')
    category = models.CharField(max_length=20, choices=TemplateCategory.choices)
    status = models.CharField(
        max_length=20,
        choices=TemplateStatus.choices,
        default=TemplateStatus.PENDING
    )
    
    components = models.JSONField(default=list)
    
    class Meta:
        db_table = 'whatsapp_templates'
        verbose_name = 'Message Template'
        verbose_name_plural = 'Message Templates'
        unique_together = ['account', 'name', 'language']

    def __str__(self):
        return f"{self.name} ({self.language}) - {self.status}"
