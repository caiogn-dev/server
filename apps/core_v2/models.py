""" Core v2 - Models completos e independentes. """

import uuid
from django.db import models
from django.conf import settings


class BaseModel(models.Model):
    """Base model com campos comuns."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='%(class)s_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='%(class)s_updated'
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']


class AuditLog(models.Model):
    """Log de auditoria."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['action', 'created_at']),
        ]
