from django.db import models

from apps.core.models import BaseModel


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
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='messages',
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages',
    )

    whatsapp_message_id = models.CharField(max_length=100, unique=True, db_index=True)
    direction = models.CharField(max_length=10, choices=MessageDirection.choices)
    message_type = models.CharField(max_length=20, choices=MessageType.choices)
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING,
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
    processed_by_agent = models.BooleanField(default=False, help_text='Processado pelo agente IA')

    class Meta:
        app_label = 'whatsapp'
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
