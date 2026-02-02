"""
Celery tasks for messaging.
"""
import logging
from celery import shared_task
from django.utils import timezone

from .dispatcher import MessageDispatcher
from .models import Message

logger = logging.getLogger(__name__)


@shared_task(name='messaging.process_scheduled_messages')
def process_scheduled_messages(batch_size: int = 100):
    """
    Process scheduled messages that are due.
    Run every minute via Celery beat.
    """
    dispatcher = MessageDispatcher()
    processed = dispatcher.process_scheduled(batch_size=batch_size)
    
    if processed > 0:
        logger.info(f"Processed {processed} scheduled messages")
    
    return {'processed': processed}


@shared_task(name='messaging.retry_failed_messages')
def retry_failed_messages(max_retries: int = 3, batch_size: int = 50):
    """
    Retry failed messages.
    Run every 5 minutes via Celery beat.
    """
    dispatcher = MessageDispatcher()
    retried = dispatcher.retry_failed(
        max_retries=max_retries,
        batch_size=batch_size
    )
    
    if retried > 0:
        logger.info(f"Retried {retried} failed messages")
    
    return {'retried': retried}


@shared_task(name='messaging.send_message_async', bind=True, max_retries=3)
def send_message_async(self, message_id: str):
    """
    Send a message asynchronously.
    Used when we need to send without blocking the request.
    """
    try:
        message = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        logger.error(f"Message not found: {message_id}")
        return {'error': 'Message not found'}
    
    dispatcher = MessageDispatcher()
    
    try:
        result = dispatcher._send_via_provider(
            message,
            dispatcher.get_provider(message.channel)
        )
        return {
            'success': result.success,
            'external_id': result.external_id,
            'error': result.error_message
        }
    except Exception as e:
        logger.exception(f"Failed to send message {message_id}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            self.retry(countdown=60 * (2 ** self.request.retries))
        
        return {'error': str(e)}


@shared_task(name='messaging.cleanup_old_messages')
def cleanup_old_messages(days: int = 90):
    """
    Clean up old message logs and soft-delete old messages.
    Run daily via Celery beat.
    """
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete old logs first
    from .models import MessageLog
    logs_deleted, _ = MessageLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    
    # Soft delete old messages
    messages_updated = Message.objects.filter(
        created_at__lt=cutoff_date,
        is_active=True
    ).update(is_active=False)
    
    logger.info(f"Cleanup complete: {logs_deleted} logs deleted, {messages_updated} messages archived")
    
    return {
        'logs_deleted': logs_deleted,
        'messages_archived': messages_updated
    }


@shared_task(name='messaging.sync_message_status')
def sync_message_status(batch_size: int = 100):
    """
    Sync message status with providers for pending messages.
    Run every 10 minutes via Celery beat.
    """
    # Get pending/sent messages without final status
    messages = Message.objects.filter(
        status__in=[Message.Status.SENT, Message.Status.PENDING],
        external_id__isnull=False,
        created_at__gte=timezone.now() - timezone.timedelta(hours=24)
    )[:batch_size]
    
    updated = 0
    dispatcher = MessageDispatcher()
    
    for message in messages:
        try:
            provider = dispatcher.get_provider(message.channel)
            status = provider.get_status(message.external_id)
            
            if status:
                if status == 'delivered':
                    message.mark_delivered()
                elif status == 'read':
                    message.mark_read()
                elif status in ['failed', 'undelivered']:
                    message.mark_failed(error_message='Provider reported failure')
                
                updated += 1
        except Exception as e:
            logger.warning(f"Failed to sync status for message {message.id}: {e}")
    
    if updated > 0:
        logger.info(f"Synced status for {updated} messages")
    
    return {'synced': updated}
