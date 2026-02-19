"""
Webhook models for centralized logging and management.
"""
import uuid
from django.db import models
from apps.core.models import BaseModel


class WebhookEvent(BaseModel):
    """
    Log of all incoming webhooks for debugging and replay.
    """
    
    class Provider(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        AUTOMATION = 'automation', 'Automation'
        CUSTOM = 'custom', 'Custom'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DUPLICATE = 'duplicate', 'Duplicate'
        IGNORED = 'ignored', 'Ignored'
    
    # Provider info
    provider = models.CharField(max_length=20, choices=Provider.choices)
    event_type = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Request data
    payload = models.JSONField()
    headers = models.JSONField(default=dict)
    query_params = models.JSONField(default=dict)
    
    # Signature verification
    signature_valid = models.BooleanField(null=True)
    signature_algorithm = models.CharField(max_length=50, blank=True)
    
    # Processing
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    # Result
    handler_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)
    
    # Idempotency
    event_id = models.CharField(max_length=255, blank=True, db_index=True)
    
    # Store context (if applicable)
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )
    
    class Meta:
        db_table = 'webhook_events'
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'event_type']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['event_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.provider}: {self.event_type} ({self.status})"


class WebhookEndpoint(BaseModel):
    """
    Configuration for webhook endpoints.
    """
    
    class Provider(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        CUSTOM = 'custom', 'Custom'
    
    # Identification
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    path = models.CharField(max_length=100, unique=True, help_text="URL path segment")
    
    # Security
    secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="Secret for signature verification"
    )
    verify_token = models.CharField(
        max_length=255,
        blank=True,
        help_text="Verification token (for challenge-response)"
    )
    signature_header = models.CharField(
        max_length=100,
        blank=True,
        default='X-Hub-Signature-256',
        help_text="Header containing signature"
    )
    
    # Handler configuration
    handler_class = models.CharField(
        max_length=255,
        help_text="Python path to handler class"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    log_payloads = models.BooleanField(default=True)
    
    # Stats
    total_received = models.PositiveIntegerField(default=0)
    total_processed = models.PositiveIntegerField(default=0)
    total_failed = models.PositiveIntegerField(default=0)
    last_received_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = 'webhook_endpoints'
        verbose_name = 'Webhook Endpoint'
        verbose_name_plural = 'Webhook Endpoints'
        ordering = ['provider', 'name']

    def __str__(self):
        return f"{self.name} ({self.provider})"


class WebhookDeliveryAttempt(BaseModel):
    """
    Track delivery attempts for webhooks we send.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        RETRYING = 'retrying', 'Retrying'
    
    # The webhook we're trying to deliver
    endpoint_url = models.URLField()
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    
    # Attempt info
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    http_status = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    
    # Timing
    attempt_number = models.PositiveIntegerField(default=1)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    # Error
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'webhook_delivery_attempts'
        verbose_name = 'Webhook Delivery Attempt'
        verbose_name_plural = 'Webhook Delivery Attempts'
        ordering = ['-created_at']


class WebhookDeadLetter(BaseModel):
    """
    Dead Letter Queue for failed webhook events.
    
    Stores events that failed processing after all retries are exhausted.
    Allows manual inspection and reprocessing.
    """
    
    class Status(models.TextChoices):
        FAILED = 'failed', 'Failed'
        REPROCESSING = 'reprocessing', 'Reprocessing'
        RESOLVED = 'resolved', 'Resolved'
        DISCARDED = 'discarded', 'Discarded'
    
    class FailureReason(models.TextChoices):
        PROCESSING_ERROR = 'processing_error', 'Processing Error'
        TIMEOUT = 'timeout', 'Timeout'
        VALIDATION_ERROR = 'validation_error', 'Validation Error'
        EXTERNAL_SERVICE_ERROR = 'external_service_error', 'External Service Error'
        NETWORK_ERROR = 'network_error', 'Network Error'
        UNKNOWN = 'unknown', 'Unknown'
    
    # Original event reference
    original_event = models.ForeignKey(
        WebhookEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dead_letter_entries'
    )
    
    # Event data (denormalized for durability)
    provider = models.CharField(max_length=20, choices=WebhookEvent.Provider.choices)
    event_type = models.CharField(max_length=100, db_index=True)
    event_id = models.CharField(max_length=255, blank=True, db_index=True)
    payload = models.JSONField()
    headers = models.JSONField(default=dict)
    query_params = models.JSONField(default=dict)
    
    # Failure details
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.FAILED
    )
    failure_reason = models.CharField(
        max_length=30,
        choices=FailureReason.choices,
        default=FailureReason.UNKNOWN
    )
    error_message = models.TextField()
    error_traceback = models.TextField(blank=True)
    
    # Retry tracking
    retry_count = models.PositiveIntegerField(default=0)
    max_retries_reached = models.BooleanField(default=False)
    last_retry_at = models.DateTimeField(null=True, blank=True)
    
    # Reprocessing
    reprocessed_at = models.DateTimeField(null=True, blank=True)
    reprocessed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reprocessed_webhooks'
    )
    reprocessing_result = models.JSONField(default=dict, blank=True)
    
    # Store context
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dead_letter_webhooks'
    )
    
    # Metadata for analysis
    failure_signature = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Hash of error type + message for grouping similar failures"
    )
    
    class Meta:
        db_table = 'webhook_dead_letter'
        verbose_name = 'Webhook Dead Letter'
        verbose_name_plural = 'Webhook Dead Letters'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'failure_reason']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['failure_signature']),
            models.Index(fields=['created_at']),
            models.Index(fields=['event_id']),
        ]
    
    def __str__(self):
        return f"DLQ: {self.provider}:{self.event_type} - {self.failure_reason}"
    
    def save(self, *args, **kwargs):
        # Generate failure signature
        if not self.failure_signature and self.error_message:
            import hashlib
            signature = f"{self.failure_reason}:{self.error_message[:100]}"
            self.failure_signature = hashlib.md5(signature.encode()).hexdigest()[:16]
        super().save(*args, **kwargs)
    
    def can_reprocess(self) -> bool:
        """Check if this entry can be reprocessed."""
        return self.status in [self.Status.FAILED, self.Status.DISCARDED]
    
    def mark_reprocessing(self, user=None):
        """Mark as being reprocessed."""
        self.status = self.Status.REPROCESSING
        self.last_retry_at = timezone.now()
        self.retry_count += 1
        if user:
            self.reprocessed_by = user
        self.save(update_fields=[
            'status', 'last_retry_at', 'retry_count', 'reprocessed_by', 'updated_at'
        ])
    
    def mark_resolved(self, result: dict = None):
        """Mark as successfully reprocessed."""
        self.status = self.Status.RESOLVED
        self.reprocessed_at = timezone.now()
        if result:
            self.reprocessing_result = result
        self.save(update_fields=['status', 'reprocessed_at', 'reprocessing_result', 'updated_at'])
    
    def mark_failed_again(self, error_message: str, traceback: str = None):
        """Mark as failed after reprocessing attempt."""
        self.status = self.Status.FAILED
        self.error_message = error_message
        if traceback:
            self.error_traceback = traceback
        self.save(update_fields=['status', 'error_message', 'error_traceback', 'updated_at'])


class WebhookOutbox(BaseModel):
    """
    Outbox Pattern for reliable webhook delivery.
    
    Webhooks are first persisted to the outbox, then processed asynchronously.
    This ensures atomicity between business operations and webhook delivery.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        SCHEDULED = 'scheduled', 'Scheduled'
    
    class Priority(models.IntegerChoices):
        LOW = 1, 'Low'
        NORMAL = 5, 'Normal'
        HIGH = 10, 'High'
        CRITICAL = 20, 'Critical'
    
    # Event details
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    
    # Target
    endpoint_url = models.URLField()
    headers = models.JSONField(default=dict)
    secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="Secret for HMAC signature"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    priority = models.IntegerField(
        choices=Priority.choices,
        default=Priority.NORMAL
    )
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    
    # Processing
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    
    # Retry logic
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    # Result
    http_status = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    # Context
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='webhook_outbox'
    )
    source_model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Model that triggered the webhook (e.g., 'stores.StoreOrder')"
    )
    source_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="ID of the source record"
    )
    
    # Idempotency
    idempotency_key = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Unique key to prevent duplicate processing"
    )
    
    class Meta:
        db_table = 'webhook_outbox'
        verbose_name = 'Webhook Outbox'
        verbose_name_plural = 'Webhook Outbox'
        ordering = ['-priority', 'created_at']
        indexes = [
            models.Index(fields=['status', 'priority', 'created_at']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['idempotency_key']),
            models.Index(fields=['store', 'status']),
            models.Index(fields=['event_type', 'status']),
        ]
    
    def __str__(self):
        return f"Outbox: {self.event_type} -> {self.endpoint_url[:50]}... ({self.status})"
    
    def generate_signature(self) -> str:
        """Generate HMAC signature for the payload."""
        if not self.secret:
            return ''
        import hmac
        import hashlib
        import json
        
        payload_bytes = json.dumps(self.payload, sort_keys=True).encode()
        signature = hmac.new(
            self.secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def mark_processing(self):
        """Mark as being processed."""
        self.status = self.Status.PROCESSING
        self.processing_started_at = timezone.now()
        self.save(update_fields=['status', 'processing_started_at', 'updated_at'])
    
    def mark_sent(self, http_status: int, response_body: str = ''):
        """Mark as successfully sent."""
        self.status = self.Status.SENT
        self.processed_at = timezone.now()
        self.http_status = http_status
        self.response_body = response_body[:1000]  # Limit storage
        self.save(update_fields=[
            'status', 'processed_at', 'http_status', 'response_body', 'updated_at'
        ])
    
    def mark_failed(self, error_message: str, schedule_retry: bool = True):
        """Mark as failed and schedule retry if applicable."""
        self.retry_count += 1
        self.error_message = error_message[:500]
        
        if self.retry_count >= self.max_retries:
            self.status = self.Status.FAILED
        elif schedule_retry:
            self.status = self.Status.SCHEDULED
            # Exponential backoff: 5s, 25s, 125s
            delay_seconds = 5 ** self.retry_count
            self.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
        else:
            self.status = self.Status.FAILED
        
        self.save(update_fields=[
            'status', 'retry_count', 'error_message', 'next_retry_at', 'updated_at'
        ])
    
    def to_delivery_attempt(self) -> WebhookDeliveryAttempt:
        """Convert to a delivery attempt record."""
        return WebhookDeliveryAttempt.objects.create(
            endpoint_url=self.endpoint_url,
            event_type=self.event_type,
            payload=self.payload,
            status=WebhookDeliveryAttempt.Status.PENDING,
            attempt_number=self.retry_count + 1
        )


# Import necessário para os modelos
from django.utils import timezone
from datetime import timedelta
