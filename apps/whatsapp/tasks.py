"""
Celery tasks for WhatsApp app.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.whatsapp.tasks.cleanup_old_webhook_events')
def cleanup_old_webhook_events():
    """
    Clean up webhook events older than 30 days.
    """
    from .models import WebhookEvent
    
    cutoff_date = timezone.now() - timedelta(days=30)
    deleted_count, _ = WebhookEvent.objects.filter(
        created_at__lt=cutoff_date,
        processed=True
    ).delete()
    
    logger.info(f"Cleaned up {deleted_count} old webhook events")
    return deleted_count


@shared_task(name='apps.whatsapp.tasks.sync_message_statuses')
def sync_message_statuses():
    """
    Sync message statuses for pending messages.
    """
    from .models import Message
    
    # Find messages that are pending for more than 5 minutes
    cutoff_time = timezone.now() - timedelta(minutes=5)
    pending_messages = Message.objects.filter(
        status='pending',
        created_at__lt=cutoff_time
    ).count()
    
    logger.info(f"Found {pending_messages} pending messages to check")
    return pending_messages


@shared_task(name='apps.whatsapp.tasks.send_message_async')
def send_message_async(account_id: str, to_number: str, message_type: str, content: dict):
    """
    Send a WhatsApp message asynchronously.
    """
    from .models import WhatsAppAccount
    from .services.message_service import MessageService
    
    try:
        account = WhatsAppAccount.objects.get(id=account_id)
        service = MessageService(account)
        
        if message_type == 'text':
            result = service.send_text(to_number, content.get('text', ''))
        elif message_type == 'template':
            result = service.send_template(
                to_number,
                content.get('template_name'),
                content.get('language', 'pt_BR'),
                content.get('components', [])
            )
        else:
            logger.error(f"Unknown message type: {message_type}")
            return None
            
        logger.info(f"Message sent to {to_number}: {result}")
        return result
        
    except WhatsAppAccount.DoesNotExist:
        logger.error(f"WhatsApp account not found: {account_id}")
        return None
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise


@shared_task(name='apps.whatsapp.tasks.process_webhook_event')
def process_webhook_event(event_id: str):
    """
    Process a webhook event asynchronously.
    """
    from .models import WebhookEvent
    from .services.webhook_service import WebhookService
    
    try:
        event = WebhookEvent.objects.get(id=event_id)
        if event.processed:
            logger.info(f"Event {event_id} already processed")
            return
            
        service = WebhookService()
        service.process_event(event)
        
        event.processed = True
        event.save(update_fields=['processed'])
        
        logger.info(f"Processed webhook event: {event_id}")
        
    except WebhookEvent.DoesNotExist:
        logger.error(f"Webhook event not found: {event_id}")
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")
        raise
