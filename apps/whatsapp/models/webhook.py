from django.db import models

from apps.core.models import BaseModel


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
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='webhook_events',
        null=True,
        blank=True,
    )

    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )

    payload = models.JSONField()
    headers = models.JSONField(default=dict)

    processed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    related_message = models.ForeignKey(
        'whatsapp.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events',
    )

    class Meta:
        app_label = 'whatsapp'
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
