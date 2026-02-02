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
