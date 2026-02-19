"""
Signals for webhook processing.

- Automatically move failed events to Dead Letter Queue
- Auto-retry transient failures
- Send alerts on critical failure patterns
"""
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import WebhookEvent, WebhookDeadLetter, WebhookOutbox
from .tasks import reprocess_dead_letter_entry

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WebhookEvent)
def handle_failed_webhook_event(sender, instance, created, **kwargs):
    """
    Automatically move failed webhook events to Dead Letter Queue.
    
    This ensures failed events are not lost and can be:
    - Inspected manually
    - Reprocessed later
    - Analyzed for patterns
    """
    if not created and instance.status == WebhookEvent.Status.FAILED:
        # Check if already in DLQ
        existing = WebhookDeadLetter.objects.filter(
            original_event=instance
        ).first()
        
        if existing:
            # Update existing entry
            existing.retry_count = instance.retry_count
            existing.error_message = instance.error_message
            existing.error_traceback = instance.error_traceback
            existing.last_retry_at = timezone.now()
            
            if instance.retry_count >= 3:
                existing.max_retries_reached = True
            
            existing.save(update_fields=[
                'retry_count', 'error_message', 'error_traceback', 
                'last_retry_at', 'max_retries_reached', 'updated_at'
            ])
            
            logger.debug(f"Updated DLQ entry for event {instance.id}")
        else:
            # Create new DLQ entry
            failure_reason = _classify_failure(instance.error_message)
            
            dlq_entry = WebhookDeadLetter.objects.create(
                original_event=instance,
                provider=instance.provider,
                event_type=instance.event_type,
                event_id=instance.event_id,
                payload=instance.payload,
                headers=instance.headers,
                query_params=instance.query_params,
                status=WebhookDeadLetter.Status.FAILED,
                failure_reason=failure_reason,
                error_message=instance.error_message or 'Unknown error',
                error_traceback=instance.error_traceback,
                retry_count=instance.retry_count,
                max_retries_reached=instance.retry_count >= 3,
                store=instance.store,
            )
            
            logger.info(f"Created DLQ entry {dlq_entry.id} for failed event {instance.id}")
            
            # Auto-retry transient failures
            if failure_reason in [
                WebhookDeadLetter.FailureReason.NETWORK_ERROR,
                WebhookDeadLetter.FailureReason.TIMEOUT,
            ] and instance.retry_count < 3:
                # Schedule retry after 5 minutes
                reprocess_dead_letter_entry.apply_async(
                    args=[str(dlq_entry.id)],
                    countdown=300  # 5 minutes
                )
                logger.info(f"Scheduled auto-retry for DLQ entry {dlq_entry.id}")


@receiver(post_save, sender=WebhookOutbox)
def handle_failed_outbox_entry(sender, instance, created, **kwargs):
    """
    Handle failed outbox entries.
    
    - Alert on repeated failures
    - Escalate critical failures
    """
    if not created and instance.status == WebhookOutbox.Status.FAILED:
        # Count recent failures for this endpoint
        recent_failures = WebhookOutbox.objects.filter(
            endpoint_url=instance.endpoint_url,
            status=WebhookOutbox.Status.FAILED,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        
        # Alert on high failure rate
        if recent_failures >= 10:
            logger.error(
                f"ALERT: High webhook failure rate for {instance.endpoint_url}: "
                f"{recent_failures} failures in the last hour"
            )
            # TODO: Send alert to monitoring system (PagerDuty, Slack, etc.)
        
        # Log for debugging
        logger.warning(
            f"Outbox entry {instance.id} failed after {instance.retry_count} retries: "
            f"{instance.error_message[:200]}"
        )


@receiver(pre_save, sender=WebhookDeadLetter)
def check_critical_failure_pattern(sender, instance, **kwargs):
    """
    Check for critical failure patterns and alert if necessary.
    """
    if instance.pk:  # Only for updates
        return
    
    # Count failures in the last hour
    recent_failures = WebhookDeadLetter.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1),
        status=WebhookDeadLetter.Status.FAILED
    ).count()
    
    # Alert thresholds
    if recent_failures == 50:  # First threshold
        logger.error(f"WARNING: {recent_failures} webhook failures in the last hour")
    elif recent_failures == 100:  # Critical threshold
        logger.error(f"CRITICAL: {recent_failures} webhook failures in the last hour!")
        # TODO: Send critical alert
    elif recent_failures == 500:  # Emergency threshold
        logger.error(f"EMERGENCY: {recent_failures} webhook failures in the last hour! "
                    f"Consider disabling webhooks temporarily.")
        # TODO: Send emergency alert, possibly auto-disable


def _classify_failure(error_message: str) -> str:
    """
    Classify the failure reason based on error message.
    """
    if not error_message:
        return WebhookDeadLetter.FailureReason.UNKNOWN
    
    error_lower = error_message.lower()
    
    # Network errors
    if any(kw in error_lower for kw in ['connection', 'timeout', 'network', 'unreachable', 'refused']):
        return WebhookDeadLetter.FailureReason.NETWORK_ERROR
    
    # External service errors
    if any(kw in error_lower for kw in ['503', '502', '504', 'bad gateway', 'service unavailable']):
        return WebhookDeadLetter.FailureReason.EXTERNAL_SERVICE_ERROR
    
    # Validation errors
    if any(kw in error_lower for kw in ['validation', 'invalid', 'schema', 'required']):
        return WebhookDeadLetter.FailureReason.VALIDATION_ERROR
    
    # Timeout (specific)
    if 'timeout' in error_lower or 'timed out' in error_lower:
        return WebhookDeadLetter.FailureReason.TIMEOUT
    
    return WebhookDeadLetter.FailureReason.PROCESSING_ERROR
