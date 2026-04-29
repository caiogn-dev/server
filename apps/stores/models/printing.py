"""
Printing models for automatic order printing.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class StorePrintAgent(BaseModel):
    """Local print agent installed on a store workstation."""

    class AgentStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        DISABLED = 'disabled', 'Disabled'

    class Platform(models.TextChoices):
        WINDOWS = 'windows', 'Windows'
        LINUX = 'linux', 'Linux'
        MACOS = 'macos', 'macOS'
        OTHER = 'other', 'Other'

    class ConnectionMode(models.TextChoices):
        WINDOWS_PRINTER = 'windows_printer', 'Windows Printer'
        USB_DIRECT = 'usb_direct', 'USB Direct'
        NETWORK = 'network', 'Network'

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='print_agents',
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    status = models.CharField(
        max_length=20,
        choices=AgentStatus.choices,
        default=AgentStatus.ACTIVE,
    )
    station = models.CharField(max_length=50, default='kitchen')
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.WINDOWS,
    )
    connection_mode = models.CharField(
        max_length=30,
        choices=ConnectionMode.choices,
        default=ConnectionMode.WINDOWS_PRINTER,
    )
    printer_name = models.CharField(max_length=255, blank=True)
    printer_host = models.CharField(max_length=255, blank=True)
    printer_port = models.PositiveIntegerField(default=9100)
    poll_interval_seconds = models.PositiveIntegerField(default=2)
    max_retries = models.PositiveIntegerField(default=3)
    api_key_prefix = models.CharField(max_length=32, unique=True, db_index=True)
    api_key_hash = models.CharField(max_length=64)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_ip = models.GenericIPAddressField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    app_version = models.CharField(max_length=50, blank=True)
    host_name = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'store_print_agents'
        verbose_name = 'Store Print Agent'
        verbose_name_plural = 'Store Print Agents'
        constraints = [
            models.UniqueConstraint(
                fields=['store', 'slug'],
                name='store_print_agent_slug_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['store', 'status'], name='print_agent_store_status_idx'),
            models.Index(fields=['store', 'station'], name='print_agent_store_station_idx'),
        ]

    def __str__(self) -> str:
        return f"{self.store.slug}:{self.station}:{self.name}"

    @staticmethod
    def _hash_secret(secret: str) -> str:
        return hashlib.sha256(secret.encode('utf-8')).hexdigest()

    @classmethod
    def generate_api_key(cls) -> tuple[str, str, str]:
        prefix = f"pa_{secrets.token_hex(6)}"
        secret = secrets.token_urlsafe(32)
        raw_key = f"{prefix}.{secret}"
        return raw_key, prefix, cls._hash_secret(secret)

    def rotate_api_key(self) -> str:
        raw_key, prefix, hashed = self.generate_api_key()
        self.api_key_prefix = prefix
        self.api_key_hash = hashed
        self.save(update_fields=['api_key_prefix', 'api_key_hash', 'updated_at'])
        return raw_key

    def verify_api_key(self, raw_key: str) -> bool:
        try:
            prefix, secret = raw_key.split('.', 1)
        except ValueError:
            return False

        if prefix != self.api_key_prefix:
            return False

        expected = self._hash_secret(secret)
        return hmac.compare_digest(expected, self.api_key_hash)

    def mark_seen(self, *, ip_address: str = '', app_version: str = '', host_name: str = '') -> None:
        self.last_seen_at = timezone.now()
        if ip_address:
            self.last_seen_ip = ip_address
        if app_version:
            self.app_version = app_version
        if host_name:
            self.host_name = host_name
        self.save(update_fields=[
            'last_seen_at',
            'last_seen_ip',
            'app_version',
            'host_name',
            'updated_at',
        ])


class StorePrintJob(BaseModel):
    """Queued print jobs to be consumed by a local print agent."""

    class JobStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CLAIMED = 'claimed', 'Claimed'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class Template(models.TextChoices):
        KITCHEN_TICKET = 'kitchen_ticket', 'Kitchen Ticket'
        CUSTOMER_RECEIPT = 'customer_receipt', 'Customer Receipt'

    class Source(models.TextChoices):
        ORDER_CREATED = 'order_created', 'Order Created'
        MANUAL_REPRINT = 'manual_reprint', 'Manual Reprint'
        TEST = 'test', 'Test'

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='print_jobs',
    )
    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.CASCADE,
        related_name='print_jobs',
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )
    station = models.CharField(max_length=50, default='kitchen')
    template = models.CharField(
        max_length=40,
        choices=Template.choices,
        default=Template.KITCHEN_TICKET,
    )
    source = models.CharField(
        max_length=30,
        choices=Source.choices,
        default=Source.ORDER_CREATED,
    )
    dedupe_key = models.CharField(max_length=255, blank=True, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict)
    claimed_by = models.ForeignKey(
        'stores.StorePrintAgent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='claimed_jobs',
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    last_error = models.TextField(blank=True)
    printer_name = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'store_print_jobs'
        verbose_name = 'Store Print Job'
        verbose_name_plural = 'Store Print Jobs'
        indexes = [
            models.Index(fields=['store', 'status', 'available_at'], name='pr_job_store_status_idx'),
            models.Index(fields=['store', 'station', 'status'], name='pr_job_store_station_idx'),
            models.Index(fields=['order', 'template'], name='print_job_order_template_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['dedupe_key'],
                condition=~models.Q(dedupe_key=''),
                name='store_print_job_dedupe_key_unique',
            ),
        ]

    def __str__(self) -> str:
        return f"{self.store.slug}:{self.station}:{self.template}:{self.status}"

    def claim(self, agent: StorePrintAgent) -> None:
        self.status = self.JobStatus.CLAIMED
        self.claimed_by = agent
        self.claimed_at = timezone.now()
        self.attempts += 1
        self.save(update_fields=[
            'status',
            'claimed_by',
            'claimed_at',
            'attempts',
            'updated_at',
        ])

    def complete(self, *, printer_name: str = '', metadata: dict | None = None) -> None:
        payload_metadata = self.metadata or {}
        if metadata:
            payload_metadata.update(metadata)
        self.status = self.JobStatus.COMPLETED
        self.printed_at = timezone.now()
        self.last_error = ''
        if printer_name:
            self.printer_name = printer_name
        self.metadata = payload_metadata
        self.save(update_fields=[
            'status',
            'printed_at',
            'last_error',
            'printer_name',
            'metadata',
            'updated_at',
        ])

    def fail(self, *, error_message: str, retryable: bool = True, retry_delay_seconds: int = 15) -> None:
        self.last_error = error_message[:4000]
        self.failed_at = timezone.now()
        if retryable and self.attempts < self.max_attempts:
            self.status = self.JobStatus.PENDING
            self.available_at = timezone.now() + timedelta(seconds=retry_delay_seconds)
        else:
            self.status = self.JobStatus.FAILED
        self.save(update_fields=[
            'status',
            'last_error',
            'failed_at',
            'available_at',
            'updated_at',
        ])
