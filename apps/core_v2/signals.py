"""
Core v2 - Signals.

Automatically handles audit logging and other side effects.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import AuditLog


@receiver(post_save)
def log_create_update(sender, instance, created, **kwargs):
    """
    Log create and update actions.
    
    Automatically creates AuditLog entries for model changes.
    """
    # Skip AuditLog itself to avoid recursion
    if sender == AuditLog:
        return
    
    # Skip models that shouldn't be logged
    if sender._meta.app_label in ['sessions', 'contenttypes', 'admin']:
        return
    
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    
    # Get current user from thread local if available
    user = getattr(settings, '_CURRENT_USER', None)
    
    # Build entity representation
    entity_repr = str(instance) if hasattr(instance, '__str__') else f"{sender.__name__}({instance.pk})"
    
    AuditLog.objects.create(
        user=user,
        action=action,
        entity_type=sender.__name__,
        entity_id=str(instance.pk),
        entity_repr=entity_repr[:255],
        new_data=_instance_to_dict(instance),
    )


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    """
    Log delete actions.
    """
    # Skip AuditLog itself to avoid recursion
    if sender == AuditLog:
        return
    
    # Skip models that shouldn't be logged
    if sender._meta.app_label in ['sessions', 'contenttypes', 'admin']:
        return
    
    # Get current user from thread local if available
    user = getattr(settings, '_CURRENT_USER', None)
    
    # Build entity representation
    entity_repr = str(instance) if hasattr(instance, '__str__') else f"{sender.__name__}({instance.pk})"
    
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.DELETE,
        entity_type=sender.__name__,
        entity_id=str(instance.pk),
        entity_repr=entity_repr[:255],
        previous_data=_instance_to_dict(instance),
    )


def _instance_to_dict(instance):
    """
    Convert model instance to dictionary for logging.
    """
    from django.db import models
    
    data = {}
    for field in instance._meta.fields:
        value = getattr(instance, field.name)
        
        # Handle different field types
        if isinstance(value, models.Model):
            data[field.name] = str(value.pk)
        elif hasattr(value, 'isoformat'):
            data[field.name] = value.isoformat()
        elif value is not None:
            data[field.name] = str(value)
        else:
            data[field.name] = None
    
    return data
