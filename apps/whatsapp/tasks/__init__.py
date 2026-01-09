"""
WhatsApp Celery tasks.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_webhook_event(self, event_id: str):
    """Process a webhook event asynchronously."""
    from ..models import WebhookEvent, Message
    from ..services import WebhookService, MessageService
    from ..repositories import WebhookEventRepository
    from apps.langflow.services import LangflowService
    from apps.conversations.services import ConversationService
    
    webhook_repo = WebhookEventRepository()
    message_service = MessageService()
    
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
        
        webhook_repo.mark_as_processing(event)
        
        if event.event_type == WebhookEvent.EventType.MESSAGE:
            _process_message_event(event, message_service)
        elif event.event_type == WebhookEvent.EventType.STATUS:
            _process_status_event(event, message_service)
        elif event.event_type == WebhookEvent.EventType.ERROR:
            _process_error_event(event, message_service)
        
        webhook_repo.mark_as_completed(event)
        logger.info(f"Webhook event processed: {event_id}")
        
    except Exception as e:
        logger.error(f"Error processing webhook event {event_id}: {str(e)}")
        webhook_repo.mark_as_failed(event, str(e))
        raise self.retry(exc=e)


def _process_message_event(event, message_service):
    """Process a message webhook event."""
    from apps.langflow.services import LangflowService
    from apps.conversations.services import ConversationService
    from apps.automation.services import AutomationService
    
    payload = event.payload
    message_data = payload.get('message', {})
    contact_info = payload.get('contact', {})
    
    message = message_service.process_inbound_message(
        account=event.account,
        message_data=message_data
    )
    
    event.related_message = message
    event.save(update_fields=['related_message'])
    
    conversation_service = ConversationService()
    conversation = conversation_service.get_or_create_conversation(
        account=event.account,
        phone_number=message.from_number,
        contact_name=contact_info.get('profile', {}).get('name', '')
    )
    
    message.conversation = conversation
    message.save(update_fields=['conversation'])
    
    # Try automation service first (for companies with CompanyProfile)
    try:
        automation_service = AutomationService()
        automation_response = automation_service.handle_incoming_message(
            account_id=str(event.account.id),
            from_number=message.from_number,
            message_text=message.text_body or '',
            message_type=message.message_type,
            message_data=message_data
        )
        
        # If automation handled it, we're done
        if automation_response:
            logger.info(f"Message handled by automation service: {message.id}")
            return
    except Exception as e:
        logger.warning(f"Automation service error: {str(e)}")
    
    # Fall back to Langflow if enabled and automation didn't handle it
    if event.account.auto_response_enabled and not message.processed_by_langflow:
        process_message_with_langflow.delay(str(message.id))


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_message_with_langflow(self, message_id: str):
    """Process a message with Langflow."""
    from ..models import Message
    from ..repositories import MessageRepository
    from apps.langflow.services import LangflowService
    from apps.conversations.services import ConversationService
    
    message_repo = MessageRepository()
    
    try:
        message = message_repo.get_by_id(message_id)
        if not message:
            logger.error(f"Message not found: {message_id}")
            return
        
        if message.processed_by_langflow:
            logger.info(f"Message already processed by Langflow: {message_id}")
            return
        
        account = message.account
        
        if not account.default_langflow_flow_id:
            logger.info(f"No Langflow flow configured for account: {account.id}")
            return
        
        conversation_service = ConversationService()
        
        if message.conversation and message.conversation.mode == 'human':
            logger.info(f"Conversation in human mode, skipping Langflow: {message_id}")
            return
        
        langflow_service = LangflowService()
        
        context = {
            'account_id': str(account.id),
            'conversation_id': str(message.conversation.id) if message.conversation else None,
            'from_number': message.from_number,
            'message_type': message.message_type,
        }
        
        response = langflow_service.process_message(
            flow_id=str(account.default_langflow_flow_id),
            message=message.text_body,
            context=context
        )
        
        message_repo.mark_as_processed_by_langflow(message)
        
        if response and response.get('response'):
            send_langflow_response.delay(
                str(account.id),
                message.from_number,
                response['response'],
                str(message.whatsapp_message_id)
            )
        
        logger.info(f"Message processed by Langflow: {message_id}")
        
    except Exception as e:
        logger.error(f"Error processing message with Langflow {message_id}: {str(e)}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_langflow_response(self, account_id: str, to: str, response_text: str, reply_to: str = None):
    """Send Langflow response as WhatsApp message."""
    from ..services import MessageService
    
    try:
        message_service = MessageService()
        message_service.send_text_message(
            account_id=account_id,
            to=to,
            text=response_text,
            reply_to=reply_to,
            metadata={'source': 'langflow'}
        )
        logger.info(f"Langflow response sent to {to}")
        
    except Exception as e:
        logger.error(f"Error sending Langflow response: {str(e)}")
        raise self.retry(exc=e)


def _process_status_event(event, message_service):
    """Process a status update webhook event."""
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
    """Process an error webhook event."""
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
