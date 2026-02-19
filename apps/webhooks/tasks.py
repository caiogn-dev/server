"""
Celery tasks for webhook processing.

Includes:
- Outbox pattern processing
- Dead Letter Queue (DLQ) management
- Webhook delivery with retries
"""
import logging
import json
import requests
import hmac
import hashlib
from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


# =============================================================================
# OUTBOX PATTERN TASKS
# =============================================================================

@shared_task(name='apps.webhooks.tasks.process_outbox')
def process_outbox(batch_size: int = 100):
    """
    Process pending webhook outbox entries.
    
    This task should be run periodically (e.g., every 10 seconds)
    to ensure timely delivery of webhooks.
    """
    from .models import WebhookOutbox
    
    # Get pending entries, ordered by priority
    pending = WebhookOutbox.objects.filter(
        status__in=[WebhookOutbox.Status.PENDING, WebhookOutbox.Status.SCHEDULED],
    ).filter(
        models.Q(scheduled_at__isnull=True) | models.Q(scheduled_at__lte=timezone.now()),
        models.Q(next_retry_at__isnull=True) | models.Q(next_retry_at__lte=timezone.now())
    ).order_by('-priority', 'created_at')[:batch_size]
    
    processed = 0
    failed = 0
    
    for entry in pending:
        try:
            process_outbox_entry.delay(entry.id)
            processed += 1
        except Exception as e:
            logger.error(f"Failed to schedule outbox entry {entry.id}: {e}")
            failed += 1
    
    logger.info(f"Outbox processing: {processed} scheduled, {failed} failed")
    return {'scheduled': processed, 'failed': failed}


@shared_task(
    name='apps.webhooks.tasks.process_outbox_entry',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(requests.RequestException,),
)
def process_outbox_entry(self, entry_id: str):
    """
    Process a single outbox entry.
    
    Sends the webhook and updates the entry status.
    """
    from .models import WebhookOutbox
    
    try:
        entry = WebhookOutbox.objects.select_for_update().get(id=entry_id)
    except WebhookOutbox.DoesNotExist:
        logger.warning(f"Outbox entry not found: {entry_id}")
        return {'status': 'not_found'}
    
    # Check if already processed
    if entry.status == WebhookOutbox.Status.SENT:
        return {'status': 'already_sent'}
    
    # Check idempotency
    if entry.idempotency_key:
        existing = WebhookOutbox.objects.filter(
            idempotency_key=entry.idempotency_key,
            status=WebhookOutbox.Status.SENT
        ).exclude(id=entry_id).first()
        
        if existing:
            entry.mark_sent(existing.http_status, existing.response_body)
            return {'status': 'deduplicated'}
    
    entry.mark_processing()
    
    try:
        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Pastita-Webhook/1.0',
            'X-Webhook-ID': str(entry.id),
            'X-Webhook-Event': entry.event_type,
            'X-Webhook-Attempt': str(entry.retry_count + 1),
        }
        
        # Add signature if secret is configured
        if entry.secret:
            headers['X-Webhook-Signature'] = entry.generate_signature()
        
        # Merge with custom headers
        headers.update(entry.headers)
        
        # Send webhook
        response = requests.post(
            entry.endpoint_url,
            json=entry.payload,
            headers=headers,
            timeout=30,
        )
        
        # Check response
        if response.status_code >= 200 and response.status_code < 300:
            entry.mark_sent(response.status_code, response.text[:1000])
            logger.info(f"Webhook sent successfully: {entry.id} -> {entry.endpoint_url}")
            return {
                'status': 'sent',
                'http_status': response.status_code,
            }
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            entry.mark_failed(error_msg, schedule_retry=True)
            
            # Retry if not exceeded max retries
            if entry.retry_count < entry.max_retries:
                raise self.retry(countdown=5 ** entry.retry_count)
            
            logger.warning(f"Webhook failed after retries: {entry.id}")
            return {
                'status': 'failed',
                'error': error_msg,
                'retries_exhausted': True,
            }
            
    except requests.Timeout:
        entry.mark_failed("Request timeout", schedule_retry=True)
        if entry.retry_count < entry.max_retries:
            raise self.retry(countdown=5 ** entry.retry_count)
        raise
        
    except requests.RequestException as e:
        entry.mark_failed(f"Request error: {str(e)}", schedule_retry=True)
        if entry.retry_count < entry.max_retries:
            raise self.retry(countdown=5 ** entry.retry_count)
        raise
        
    except Exception as e:
        logger.exception(f"Unexpected error processing outbox entry {entry_id}")
        entry.mark_failed(f"Unexpected error: {str(e)}", schedule_retry=False)
        return {
            'status': 'error',
            'error': str(e),
        }


@shared_task(name='apps.webhooks.tasks.schedule_webhook')
def schedule_webhook(
    event_type: str,
    payload: dict,
    endpoint_url: str,
    store_id: str = None,
    priority: int = 5,
    delay_seconds: int = 0,
    idempotency_key: str = None,
    headers: dict = None,
    secret: str = None,
):
    """
    Schedule a webhook for delivery via the outbox pattern.
    
    This is the main entry point for sending webhooks reliably.
    """
    from .models import WebhookOutbox
    from apps.stores.models import Store
    
    # Check for duplicate if idempotency key provided
    if idempotency_key:
        existing = WebhookOutbox.objects.filter(
            idempotency_key=idempotency_key,
            status__in=[WebhookOutbox.Status.PENDING, WebhookOutbox.Status.SCHEDULED]
        ).first()
        
        if existing:
            logger.info(f"Duplicate webhook skipped: {idempotency_key}")
            return {'status': 'duplicate', 'outbox_id': str(existing.id)}
    
    # Get store if provided
    store = None
    if store_id:
        try:
            store = Store.objects.get(id=store_id)
        except Store.DoesNotExist:
            logger.warning(f"Store not found for webhook: {store_id}")
    
    # Calculate scheduled time
    scheduled_at = None
    if delay_seconds > 0:
        scheduled_at = timezone.now() + timedelta(seconds=delay_seconds)
    
    # Create outbox entry
    with transaction.atomic():
        entry = WebhookOutbox.objects.create(
            event_type=event_type,
            payload=payload,
            endpoint_url=endpoint_url,
            store=store,
            priority=priority,
            scheduled_at=scheduled_at,
            idempotency_key=idempotency_key,
            headers=headers or {},
            secret=secret,
        )
    
    # Trigger immediate processing if no delay
    if not scheduled_at:
        process_outbox_entry.delay(str(entry.id))
    
    logger.info(f"Webhook scheduled: {entry.id} ({event_type})")
    return {
        'status': 'scheduled',
        'outbox_id': str(entry.id),
    }


@shared_task(name='apps.webhooks.tasks.process_high_priority_outbox')
def process_high_priority_outbox():
    """Process high priority outbox entries immediately."""
    from .models import WebhookOutbox
    
    high_priority = WebhookOutbox.objects.filter(
        status=WebhookOutbox.Status.PENDING,
        priority__gte=WebhookOutbox.Priority.HIGH,
    ).order_by('created_at')[:50]
    
    for entry in high_priority:
        process_outbox_entry.delay(entry.id)
    
    return {'processed': len(high_priority)}


# =============================================================================
# DEAD LETTER QUEUE TASKS
# =============================================================================

@shared_task(name='apps.webhooks.tasks.process_dead_letter')
def process_dead_letter(max_entries: int = 50, auto_reprocess: bool = False):
    """
    Process entries in the Dead Letter Queue.
    
    - Groups similar failures for analysis
    - Optionally auto-reprocess certain types of failures
    - Alerts on critical failure patterns
    """
    from .models import WebhookDeadLetter, WebhookEvent
    from django.db.models import Count
    
    # Get failed entries
    failed_entries = WebhookDeadLetter.objects.filter(
        status=WebhookDeadLetter.Status.FAILED
    ).order_by('-created_at')[:max_entries]
    
    # Group by failure signature for analysis
    failure_groups = WebhookDeadLetter.objects.filter(
        status=WebhookDeadLetter.Status.FAILED
    ).values('failure_signature', 'failure_reason').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    results = {
        'total_failed': failed_entries.count(),
        'failure_groups': list(failure_groups),
        'auto_reprocessed': 0,
        'errors': [],
    }
    
    # Auto-reprocess transient failures if enabled
    if auto_reprocess:
        transient_failures = failed_entries.filter(
            failure_reason__in=[
                WebhookDeadLetter.FailureReason.NETWORK_ERROR,
                WebhookDeadLetter.FailureReason.TIMEOUT,
            ],
            retry_count__lt=3
        )
        
        for entry in transient_failures:
            try:
                reprocess_dead_letter_entry.delay(str(entry.id))
                results['auto_reprocessed'] += 1
            except Exception as e:
                results['errors'].append(str(e))
    
    # Alert on critical patterns
    critical_count = WebhookDeadLetter.objects.filter(
        status=WebhookDeadLetter.Status.FAILED,
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    
    if critical_count > 100:
        logger.error(f"CRITICAL: {critical_count} webhook failures in the last hour!")
        # TODO: Send alert to monitoring system
    
    return results


@shared_task(
    name='apps.webhooks.tasks.reprocess_dead_letter_entry',
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def reprocess_dead_letter_entry(self, entry_id: str, user_id: int = None):
    """
    Reprocess a single Dead Letter Queue entry.
    """
    from .models import WebhookDeadLetter
    from .dispatcher import WebhookDispatcherView
    
    try:
        entry = WebhookDeadLetter.objects.get(id=entry_id)
    except WebhookDeadLetter.DoesNotExist:
        return {'status': 'not_found'}
    
    if not entry.can_reprocess():
        return {'status': 'cannot_reprocess', 'current_status': entry.status}
    
    # Get user if provided
    user = None
    if user_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass
    
    entry.mark_reprocessing(user)
    
    try:
        # If there's an original event, try to process it
        if entry.original_event:
            handler_class = WebhookDispatcherView._handlers.get(entry.provider)
            if handler_class:
                handler = handler_class()
                result = handler.handle(entry.original_event, entry.payload, entry.headers)
                
                entry.mark_resolved({
                    'success': True,
                    'handler_result': result,
                    'reprocessed_at': timezone.now().isoformat(),
                })
                
                # Update original event
                entry.original_event.status = WebhookEvent.Status.COMPLETED
                entry.original_event.save(update_fields=['status'])
                
                return {'status': 'resolved'}
        
        # Otherwise, treat as a new webhook delivery
        schedule_webhook.delay(
            event_type=entry.event_type,
            payload=entry.payload,
            endpoint_url=entry.original_event.store.webhook_url if entry.original_event and entry.original_event.store else '',
            priority=WebhookOutbox.Priority.HIGH,
        )
        
        entry.mark_resolved({'success': True, 'scheduled': True})
        return {'status': 'scheduled_for_delivery'}
        
    except Exception as e:
        logger.exception(f"Reprocessing failed for DLQ entry {entry_id}")
        entry.mark_failed_again(str(e), self.request.traceback if self.request else '')
        return {'status': 'failed_again', 'error': str(e)}


@shared_task(name='apps.webhooks.tasks.reprocess_by_failure_signature')
def reprocess_by_failure_signature(failure_signature: str, user_id: int = None):
    """
    Reprocess all DLQ entries with a specific failure signature.
    Useful for fixing batches of similar errors.
    """
    from .models import WebhookDeadLetter
    
    entries = WebhookDeadLetter.objects.filter(
        failure_signature=failure_signature,
        status=WebhookDeadLetter.Status.FAILED
    )
    
    count = entries.count()
    scheduled = 0
    
    for entry in entries:
        try:
            reprocess_dead_letter_entry.delay(str(entry.id), user_id)
            scheduled += 1
        except Exception as e:
            logger.error(f"Failed to schedule reprocessing for {entry.id}: {e}")
    
    return {
        'total': count,
        'scheduled': scheduled,
    }


@shared_task(name='apps.webhooks.tasks.cleanup_old_dead_letter')
def cleanup_old_dead_letter(days: int = 30):
    """
    Clean up resolved/discarded DLQ entries older than specified days.
    """
    from .models import WebhookDeadLetter
    
    cutoff = timezone.now() - timedelta(days=days)
    
    deleted, _ = WebhookDeadLetter.objects.filter(
        status__in=[WebhookDeadLetter.Status.RESOLVED, WebhookDeadLetter.Status.DISCARDED],
        updated_at__lt=cutoff
    ).delete()
    
    logger.info(f"Cleaned up {deleted} old DLQ entries")
    return {'deleted': deleted}


# =============================================================================
# WEBHOOK UTILITY TASKS
# =============================================================================

@shared_task(name='apps.webhooks.tasks.cleanup_old_outbox')
def cleanup_old_outbox(days: int = 7):
    """
    Clean up sent/failed outbox entries older than specified days.
    """
    from .models import WebhookOutbox
    
    cutoff = timezone.now() - timedelta(days=days)
    
    deleted, _ = WebhookOutbox.objects.filter(
        status__in=[WebhookOutbox.Status.SENT, WebhookOutbox.Status.FAILED],
        processed_at__lt=cutoff
    ).delete()
    
    logger.info(f"Cleaned up {deleted} old outbox entries")
    return {'deleted': deleted}


# Import necessário
from django.db import models
