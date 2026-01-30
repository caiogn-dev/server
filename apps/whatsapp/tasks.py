"""
Celery tasks for WhatsApp app.
"""
from celery import shared_task
from django.db import models
from django.utils import timezone
from datetime import timedelta
import logging
import time

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
        processing_status=WebhookEvent.ProcessingStatus.COMPLETED
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
        # Verify account exists
        WhatsAppAccount.objects.get(id=account_id)
        service = MessageService()
        
        if message_type == 'text':
            result = service.send_text_message(
                account_id=account_id,
                to=to_number,
                text=content.get('text', '')
            )
        elif message_type == 'template':
            result = service.send_template_message(
                account_id=account_id,
                to=to_number,
                template_name=content.get('template_name'),
                language_code=content.get('language', 'pt_BR'),
                components=content.get('components', [])
            )
        else:
            logger.error(f"Unknown message type: {message_type}")
            return None
            
        logger.info(f"Message sent to {to_number}: {result}")
        return {'message_id': str(result.id), 'whatsapp_message_id': result.whatsapp_message_id}
        
    except WhatsAppAccount.DoesNotExist:
        logger.error(f"WhatsApp account not found: {account_id}")
        return None
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        raise


@shared_task(name='apps.whatsapp.tasks.process_webhook_event')
def process_webhook_event(event_id: str):
    """
    Process a webhook event asynchronously.
    
    This task handles:
    - MESSAGE events: Creates Message record, broadcasts to WebSocket clients
    - STATUS events: Updates message status (sent/delivered/read), broadcasts update
    - ERROR events: Logs error, broadcasts to clients
    """
    from .models import WebhookEvent
    from .services.webhook_service import WebhookService
    
    try:
        event = WebhookEvent.objects.get(id=event_id)
        
        # Check if already processed
        if event.processing_status == WebhookEvent.ProcessingStatus.COMPLETED:
            logger.info(f"Event {event_id} already processed")
            return {'status': 'skipped', 'reason': 'already_processed'}
        
        if event.processing_status == WebhookEvent.ProcessingStatus.PROCESSING:
            logger.info(f"Event {event_id} is being processed by another worker")
            return {'status': 'skipped', 'reason': 'in_progress'}
            
        service = WebhookService()
        message = service.process_event(event, post_process_inbound=True)
        
        logger.info(f"Processed webhook event: {event_id}, type: {event.event_type}")
        
        return {
            'status': 'success',
            'event_id': str(event_id),
            'event_type': event.event_type,
            'message_id': str(message.id) if message else None
        }
        
    except WebhookEvent.DoesNotExist:
        logger.error(f"Webhook event not found: {event_id}")
        return {'status': 'error', 'reason': 'not_found'}
    except Exception as e:
        logger.error(f"Error processing webhook event {event_id}: {e}", exc_info=True)
        raise


@shared_task(name='apps.whatsapp.tasks.process_pending_webhook_events')
def process_pending_webhook_events(batch_size: int = 100):
    """
    Process pending webhook events in batch.
    
    This task picks up any events that weren't processed immediately
    (e.g., due to worker unavailability).
    """
    from .models import WebhookEvent
    from .services.webhook_service import WebhookService
    
    pending_events = WebhookEvent.objects.filter(
        processing_status=WebhookEvent.ProcessingStatus.PENDING
    ).order_by('created_at')[:batch_size]
    
    processed = 0
    failed = 0
    service = WebhookService()
    
    for event in pending_events:
        try:
            service.process_event(event)
            processed += 1
        except Exception as e:
            logger.error(f"Error processing event {event.id}: {e}")
            failed += 1
    
    logger.info(f"Batch processed {processed} events, {failed} failed")
    return {'processed': processed, 'failed': failed}


@shared_task(name='apps.whatsapp.tasks.retry_failed_webhook_events')
def retry_failed_webhook_events(max_retries: int = 3, batch_size: int = 50):
    """
    Retry failed webhook events that haven't exceeded max retries.
    """
    from .models import WebhookEvent
    from .services.webhook_service import WebhookService
    
    failed_events = WebhookEvent.objects.filter(
        processing_status=WebhookEvent.ProcessingStatus.FAILED,
        retry_count__lt=max_retries
    ).order_by('created_at')[:batch_size]
    
    retried = 0
    succeeded = 0
    service = WebhookService()
    
    for event in failed_events:
        try:
            # Reset status to pending for retry
            event.processing_status = WebhookEvent.ProcessingStatus.PENDING
            event.retry_count += 1
            event.save(update_fields=['processing_status', 'retry_count', 'updated_at'])
            
            service.process_event(event)
            succeeded += 1
        except Exception as e:
            logger.error(f"Retry failed for event {event.id}: {e}")
        
        retried += 1
    
    logger.info(f"Retried {retried} events, {succeeded} succeeded")
    return {'retried': retried, 'succeeded': succeeded}


@shared_task(
    name='apps.whatsapp.tasks.send_campaign_message',
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def send_campaign_message(
    self,
    account_id: str,
    recipient_id: str,
    campaign_id: str,
    message_type: str = 'template',
    content: dict = None
):
    """
    Send a single campaign message with rate limiting.
    
    This task is designed to be called with countdown/eta to implement
    rate limiting for mass messaging campaigns.
    """
    from .models import WhatsAppAccount, Message
    from .services.message_service import MessageService
    from apps.campaigns.models import Campaign, CampaignRecipient
    
    try:
        account = WhatsAppAccount.objects.get(id=account_id)
        recipient = CampaignRecipient.objects.get(id=recipient_id)
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Check if campaign is still running
        if campaign.status != Campaign.CampaignStatus.RUNNING:
            logger.info(f"Campaign {campaign_id} is not running, skipping message")
            return {'status': 'skipped', 'reason': 'campaign_not_running'}
        
        # Check if recipient already processed
        if recipient.status != CampaignRecipient.RecipientStatus.PENDING:
            logger.info(f"Recipient {recipient_id} already processed")
            return {'status': 'skipped', 'reason': 'already_processed'}
        
        # MessageService is instantiated without arguments
        service = MessageService()
        
        if message_type == 'template' and campaign.template:
            message = service.send_template_message(
                account_id=account_id,
                to=recipient.phone_number,
                template_name=campaign.template.name,
                language_code=campaign.template.language,
                components=content.get('components', []) if content else []
            )
        else:
            text = content.get('text', '') if content else ''
            message = service.send_text_message(
                account_id=account_id,
                to=recipient.phone_number,
                text=text
            )
        
        # Update recipient status
        recipient.message_id = str(message.id)
        recipient.whatsapp_message_id = message.whatsapp_message_id
        recipient.status = CampaignRecipient.RecipientStatus.SENT
        recipient.sent_at = timezone.now()
        recipient.save()
        
        # Update campaign stats
        Campaign.objects.filter(id=campaign_id).update(
            messages_sent=models.F('messages_sent') + 1
        )
        
        logger.info(f"Campaign message sent to {recipient.phone_number}")
        return {
            'status': 'success',
            'message_id': str(message.id),
            'recipient': recipient.phone_number
        }
        
    except WhatsAppAccount.DoesNotExist:
        logger.error(f"Account not found: {account_id}")
        return {'status': 'error', 'reason': 'account_not_found'}
    except CampaignRecipient.DoesNotExist:
        logger.error(f"Recipient not found: {recipient_id}")
        return {'status': 'error', 'reason': 'recipient_not_found'}
    except Exception as e:
        logger.error(f"Error sending campaign message: {e}", exc_info=True)
        
        # Update recipient as failed
        try:
            recipient = CampaignRecipient.objects.get(id=recipient_id)
            recipient.status = CampaignRecipient.RecipientStatus.FAILED
            recipient.failed_at = timezone.now()
            recipient.error_message = str(e)
            recipient.save()
            
            Campaign.objects.filter(id=campaign_id).update(
                messages_failed=models.F('messages_failed') + 1
            )
        except Exception:
            pass
        
        # Retry with exponential backoff
        raise self.retry(exc=e)


@shared_task(name='apps.whatsapp.tasks.schedule_campaign_messages')
def schedule_campaign_messages(campaign_id: str, messages_per_minute: int = 60):
    """
    Schedule campaign messages with rate limiting.
    
    This task creates individual send_campaign_message tasks with
    appropriate delays to respect Meta's rate limits.
    
    Meta Cloud API limits:
    - Business accounts: 80 messages/second (4800/minute)
    - Standard accounts: 250 messages/day
    
    We use a conservative default of 60 messages/minute to avoid issues.
    """
    from apps.campaigns.models import Campaign, CampaignRecipient
    
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status != Campaign.CampaignStatus.RUNNING:
            logger.info(f"Campaign {campaign_id} is not running")
            return {'status': 'skipped', 'reason': 'not_running'}
        
        # Get pending recipients
        recipients = CampaignRecipient.objects.filter(
            campaign_id=campaign_id,
            status=CampaignRecipient.RecipientStatus.PENDING
        ).order_by('created_at')
        
        # Calculate delay between messages
        delay_seconds = 60.0 / messages_per_minute
        
        scheduled = 0
        for i, recipient in enumerate(recipients):
            # Calculate countdown for this message
            countdown = i * delay_seconds
            
            # Build message content
            content = {}
            if campaign.template:
                content = {
                    'components': _build_template_components(
                        campaign.message_content,
                        recipient.variables
                    )
                }
            else:
                content = {
                    'text': _personalize_message(
                        campaign.message_content.get('text', ''),
                        recipient.variables
                    )
                }
            
            # Schedule the message
            send_campaign_message.apply_async(
                args=[
                    str(campaign.account_id),
                    str(recipient.id),
                    str(campaign_id),
                    'template' if campaign.template else 'text',
                    content
                ],
                countdown=countdown
            )
            
            scheduled += 1
        
        logger.info(f"Scheduled {scheduled} messages for campaign {campaign_id}")
        return {'status': 'success', 'scheduled': scheduled}
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign not found: {campaign_id}")
        return {'status': 'error', 'reason': 'not_found'}
    except Exception as e:
        logger.error(f"Error scheduling campaign messages: {e}")
        raise


def _build_template_components(content: dict, variables: dict) -> list:
    """Build template components with personalization."""
    components = content.get('components', [])
    
    for component in components:
        if 'parameters' in component:
            for param in component['parameters']:
                if param.get('type') == 'text' and 'variable' in param:
                    var_name = param['variable']
                    param['text'] = variables.get(var_name, param.get('text', ''))
    
    return components


def _personalize_message(text: str, variables: dict) -> str:
    """Personalize message text with variables."""
    for key, value in variables.items():
        text = text.replace(f'{{{{{key}}}}}', str(value))
    return text
