"""
Signals for webhook processing.

- Automatically move failed events to Dead Letter Queue
- Auto-retry transient failures
- Send alerts on critical failure patterns
"""
import logging
import threading
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import WebhookEvent, WebhookDeadLetter, WebhookOutbox
from .tasks import reprocess_dead_letter_entry

logger = logging.getLogger(__name__)


def _send_monitoring_alert(level: str, message: str) -> None:
    """
    Fire an alert to the configured monitoring webhook (Slack/Discord/PagerDuty).

    Set MONITORING_WEBHOOK_URL in Django settings or the environment.
    If not configured, the alert is only logged (no-op at the network level).

    Executes in a daemon thread so it never blocks signal processing.

    level: "warning" | "critical" | "emergency"
    """
    from django.conf import settings
    url = getattr(settings, 'MONITORING_WEBHOOK_URL', None)
    if not url:
        return

    def _post():
        try:
            import urllib.request
            import json
            emoji = {"warning": ":warning:", "critical": ":rotating_light:", "emergency": ":skull:"}.get(level, ":bell:")
            payload = json.dumps({"text": f"{emoji} *[{level.upper()}]* {message}"}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Monitoring webhook delivery failed: %s", exc)

    t = threading.Thread(target=_post, daemon=True)
    t.start()


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
            original_event_id=str(instance.id)
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
                original_event_id=str(instance.id),
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
            msg = (
                f"High webhook failure rate for `{instance.endpoint_url}`: "
                f"{recent_failures} failures in the last hour"
            )
            logger.error("ALERT: %s", msg)
            _send_monitoring_alert("warning", msg)
        
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
    if recent_failures == 50:
        msg = f"{recent_failures} webhook failures in the last hour"
        logger.error("WARNING: %s", msg)
        _send_monitoring_alert("warning", msg)
    elif recent_failures == 100:
        msg = f"{recent_failures} webhook failures in the last hour"
        logger.error("CRITICAL: %s", msg)
        _send_monitoring_alert("critical", msg)
    elif recent_failures == 500:
        msg = f"{recent_failures} webhook failures in the last hour — consider disabling webhooks temporarily"
        logger.error("EMERGENCY: %s", msg)
        _send_monitoring_alert("emergency", msg)


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
