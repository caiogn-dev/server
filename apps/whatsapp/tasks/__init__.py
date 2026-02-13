"""
WhatsApp Celery tasks.
"""
import logging
import time
from celery import shared_task
from django.utils import timezone
from django.conf import settings
import redis

logger = logging.getLogger(__name__)

# Redis client for distributed locking
def get_redis_client():
    """Get Redis client for locking."""
    try:
        return redis.from_url(settings.CELERY_BROKER_URL)
    except Exception:
        return None

def acquire_lock(lock_name, timeout=60):
    """Acquire a distributed lock using Redis."""
    client = get_redis_client()
    if not client:
        return True  # No Redis, no lock
    
    # Try to acquire lock with NX (only if not exists)
    acquired = client.set(lock_name, "1", nx=True, ex=timeout)
    return acquired

def release_lock(lock_name):
    """Release a distributed lock."""
    client = get_redis_client()
    if client:
        client.delete(lock_name)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_webhook_event(self, event_id: str):
    """Process a webhook event asynchronously."""
    from ..models import WebhookEvent
    from ..services import WebhookService
    from ..repositories import WebhookEventRepository
    
    webhook_repo = WebhookEventRepository()
    
    try:
        event = webhook_repo.get_by_id(event_id)
        if not event:
            logger.error(f"Webhook event not found: {event_id}")
            return
        
        if event.processing_status in [
            WebhookEvent.ProcessingStatus.COMPLETED,
            WebhookEvent.ProcessingStatus.DUPLICATE
        ]:
            logger.info(f"Event already processed: {event_id}")
            return
        
        if event.processing_status == WebhookEvent.ProcessingStatus.PROCESSING:
            logger.info(f"Event is already processing: {event_id}")
            return
        
        service = WebhookService()
        service.process_event(event, post_process_inbound=True)
        
        logger.info(f"Webhook event processed: {event_id}")
        
    except Exception as e:
        logger.error(f"Error processing webhook event {event_id}: {str(e)}")
        try:
            webhook_repo.mark_as_failed(event, str(e))
        except Exception:
            logger.error("Failed to mark webhook event as failed", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_message_with_agent(self, message_id: str):
    """Process a message with AI Agent (Langchain)."""
    from ..models import Message
    from ..repositories import MessageRepository
    from apps.agents.services import AgentService
    from apps.conversations.services import ConversationService
    
    message_repo = MessageRepository()
    
    # Acquire distributed lock to prevent duplicate processing
    lock_name = f"process_message_with_agent:{message_id}"
    if not acquire_lock(lock_name, timeout=120):
        logger.info(f"Message {message_id} is already being processed by another worker")
        return
    
    try:
        message = message_repo.get_by_id(message_id)
        if not message:
            logger.error(f"Message not found: {message_id}")
            return
        
        if message.processed_by_agent:
            logger.info(f"Message already processed by AI Agent: {message_id}")
            return
        
        account = message.account
        
        if not account.default_agent:
            logger.info(f"No AI Agent configured for account: {account.id}")
            return
        
        conversation_service = ConversationService()
        
        if message.conversation and message.conversation.mode == 'human':
            logger.info(f"Conversation in human mode, skipping AI Agent: {message_id}")
            return
        
        agent = account.default_agent
        service = AgentService(agent)
        
        context = {
            'account_id': str(account.id),
            'conversation_id': str(message.conversation.id) if message.conversation else None,
            'from_number': message.from_number,
            'message_type': message.message_type,
        }
        
        response_text = service.process_message(
            message=message.text_body or '',
            session_id=str(message.conversation.id) if message.conversation else None,
            phone_number=message.from_number,
            context=context
        )
        
        message_repo.mark_as_processed_by_agent(message)
        
        if response_text:
            send_agent_response.delay(
                str(account.id),
                message.from_number,
                response_text,
                str(message.whatsapp_message_id)
            )
        
        logger.info(f"Message processed by AI Agent: {message_id}")
        
    except Exception as e:
        logger.error(f"Error processing message with AI Agent {message_id}: {str(e)}")
        raise self.retry(exc=e)
    finally:
        # Always release the lock
        release_lock(lock_name)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_agent_response(self, account_id: str, to: str, response_text: str, reply_to: str = None):
    """Send AI Agent response as WhatsApp message."""
    from ..services import MessageService
    
    try:
        message_service = MessageService()
        # Ensure phone number has + prefix for E.164 format
        formatted_to = to if to.startswith('+') else '+' + to
        
        message_service.send_text_message(
            account_id=account_id,
            to=formatted_to,
            text=response_text,
            reply_to=reply_to,
            metadata={'source': 'ai_agent'}
        )
        logger.info(f"AI Agent response sent to {to}")
        
    except Exception as e:
        logger.error(f"Error sending AI Agent response: {str(e)}")
        raise self.retry(exc=e)


def _process_status_event(event, message_service):
    """Legacy status handler (kept for backward compatibility)."""
    payload = event.payload
    
    message_id = payload.get('id')
    status = payload.get('status')
    timestamp_str = payload.get('timestamp')
    
    timestamp = None
    if timestamp_str:
        try:
            timestamp = timezone.datetime.fromtimestamp(
                int(timestamp_str),
                tz=timezone.utc
            )
        except (ValueError, TypeError):
            pass
    
    message = message_service.update_message_status(
        whatsapp_message_id=message_id,
        status=status,
        timestamp=timestamp
    )
    
    if message:
        event.related_message = message
        event.save(update_fields=['related_message'])
    
    errors = payload.get('errors', [])
    if errors and message:
        error = errors[0]
        message_service.update_message_error(
            whatsapp_message_id=message_id,
            error_code=str(error.get('code', '')),
            error_message=error.get('title', '')
        )


def _process_error_event(event, message_service):
    """Legacy error handler (kept for backward compatibility)."""
    payload = event.payload
    
    error_code = payload.get('code')
    error_title = payload.get('title')
    error_message = payload.get('message', '')
    error_details = payload.get('error_data', {})
    
    logger.error(
        f"WhatsApp API Error: {error_code} - {error_title}",
        extra={
            'error_code': error_code,
            'error_title': error_title,
            'error_message': error_message,
            'error_details': error_details,
            'account_id': str(event.account.id) if event.account else None,
        }
    )


@shared_task
def cleanup_old_webhook_events():
    """Cleanup old webhook events."""
    from ..services import WebhookService
    
    service = WebhookService()
    deleted = service.cleanup_old_events(days=30)
    logger.info(f"Cleaned up {deleted} old webhook events")


@shared_task
def sync_message_statuses():
    """Sync message statuses for pending messages."""
    from ..models import Message
    from ..repositories import MessageRepository
    
    message_repo = MessageRepository()
    
    pending_messages = message_repo.get_pending_messages(limit=100)
    
    for message in pending_messages:
        if (timezone.now() - message.created_at).total_seconds() > 300:
            message.status = Message.MessageStatus.FAILED
            message.error_message = "Message delivery timeout"
            message.failed_at = timezone.now()
            message.save()
            logger.warning(f"Message marked as failed due to timeout: {message.id}")
