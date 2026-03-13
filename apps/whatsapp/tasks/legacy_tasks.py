"""
Legacy/compatibility Celery tasks for WhatsApp.

These tasks keep old task names stable while the project migrates to the
package-based task layout under apps.whatsapp.tasks.
"""
import logging

from celery import shared_task
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='apps.whatsapp.tasks.send_message_async')
def send_message_async(account_id: str, to_number: str, message_type: str, content: dict):
    """
    Send a WhatsApp message asynchronously (legacy task name).
    """
    from ..models import WhatsAppAccount
    from ..services.message_service import MessageService

    try:
        WhatsAppAccount.objects.get(id=account_id)
        service = MessageService()

        if message_type == 'text':
            result = service.send_text_message(
                account_id=account_id,
                to=to_number,
                text=(content or {}).get('text', ''),
            )
        elif message_type == 'template':
            result = service.send_template_message(
                account_id=account_id,
                to=to_number,
                template_name=(content or {}).get('template_name'),
                language_code=(content or {}).get('language', 'pt_BR'),
                components=(content or {}).get('components', []),
            )
        else:
            logger.error("Unknown message type for async sending: %s", message_type)
            return None

        return {
            'message_id': str(result.id),
            'whatsapp_message_id': result.whatsapp_message_id,
        }
    except WhatsAppAccount.DoesNotExist:
        logger.error("WhatsApp account not found for async sending: %s", account_id)
        return None
    except Exception:
        logger.exception("Error sending async WhatsApp message")
        raise


@shared_task(name='apps.whatsapp.tasks.process_pending_webhook_events')
def process_pending_webhook_events(batch_size: int = 100):
    """
    Process pending webhook events in batch.
    """
    from ..models import WebhookEvent
    from ..services.webhook_service import WebhookService

    pending_events = WebhookEvent.objects.filter(
        processing_status=WebhookEvent.ProcessingStatus.PENDING
    ).order_by('created_at')[:batch_size]

    processed = 0
    failed = 0
    service = WebhookService()

    for event in pending_events:
        try:
            service.process_event(event, post_process_inbound=True)
            processed += 1
        except Exception:
            failed += 1
            logger.exception("Error processing pending webhook event %s", event.id)

    logger.info("Processed pending webhook events: processed=%s failed=%s", processed, failed)
    return {'processed': processed, 'failed': failed}


@shared_task(name='apps.whatsapp.tasks.retry_failed_webhook_events')
def retry_failed_webhook_events(max_retries: int = 3, batch_size: int = 50):
    """
    Retry failed webhook events that have not exceeded max retries.
    """
    from ..models import WebhookEvent
    from ..services.webhook_service import WebhookService

    failed_events = WebhookEvent.objects.filter(
        processing_status=WebhookEvent.ProcessingStatus.FAILED,
        retry_count__lt=max_retries,
    ).order_by('created_at')[:batch_size]

    retried = 0
    succeeded = 0
    service = WebhookService()

    for event in failed_events:
        retried += 1
        try:
            event.processing_status = WebhookEvent.ProcessingStatus.PENDING
            event.retry_count += 1
            event.save(update_fields=['processing_status', 'retry_count', 'updated_at'])

            service.process_event(event, post_process_inbound=True)
            succeeded += 1
        except Exception:
            logger.exception("Retry failed for webhook event %s", event.id)

    logger.info("Retried failed webhook events: retried=%s succeeded=%s", retried, succeeded)
    return {'retried': retried, 'succeeded': succeeded}


@shared_task(
    name='apps.whatsapp.tasks.send_campaign_message',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_campaign_message(
    self,
    account_id: str,
    recipient_id: str,
    campaign_id: str,
    message_type: str = 'template',
    content: dict = None,
):
    """
    Send a single campaign message with backward-compatible task name.
    """
    from ..models import WhatsAppAccount
    from ..services.message_service import MessageService
    from apps.campaigns.models import Campaign, CampaignRecipient

    try:
        account = WhatsAppAccount.objects.get(id=account_id)
        recipient = CampaignRecipient.objects.get(id=recipient_id)
        campaign = Campaign.objects.get(id=campaign_id)

        if campaign.status != Campaign.CampaignStatus.RUNNING:
            return {'status': 'skipped', 'reason': 'campaign_not_running'}

        if recipient.status != CampaignRecipient.RecipientStatus.PENDING:
            return {'status': 'skipped', 'reason': 'already_processed'}

        service = MessageService()
        payload = content or {}

        if message_type == 'template' and campaign.template:
            message = service.send_template_message(
                account_id=str(account.id),
                to=recipient.phone_number,
                template_name=campaign.template.name,
                language_code=campaign.template.language,
                components=payload.get('components', []),
            )
        else:
            message = service.send_text_message(
                account_id=str(account.id),
                to=recipient.phone_number,
                text=payload.get('text', ''),
            )

        recipient.message_id = str(message.id)
        recipient.whatsapp_message_id = message.whatsapp_message_id
        recipient.status = CampaignRecipient.RecipientStatus.SENT
        recipient.sent_at = timezone.now()
        recipient.save()

        Campaign.objects.filter(id=campaign_id).update(messages_sent=models.F('messages_sent') + 1)

        return {
            'status': 'success',
            'message_id': str(message.id),
            'recipient': recipient.phone_number,
        }
    except Exception as e:
        logger.error("Error sending campaign message: %s", e, exc_info=True)
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
            logger.exception("Failed to mark campaign recipient as failed")
        raise self.retry(exc=e)


@shared_task(name='apps.whatsapp.tasks.schedule_campaign_messages')
def schedule_campaign_messages(campaign_id: str, messages_per_minute: int = 60):
    """
    Schedule campaign messages with rate limiting (legacy task name).
    """
    from apps.campaigns.models import Campaign, CampaignRecipient

    try:
        campaign = Campaign.objects.get(id=campaign_id)
        if campaign.status != Campaign.CampaignStatus.RUNNING:
            return {'status': 'skipped', 'reason': 'not_running'}

        recipients = CampaignRecipient.objects.filter(
            campaign_id=campaign_id,
            status=CampaignRecipient.RecipientStatus.PENDING,
        ).order_by('created_at')

        # Conservative fallback to avoid division by zero/negative values
        rpm = max(1, int(messages_per_minute or 1))
        delay_seconds = 60.0 / rpm

        scheduled = 0
        for i, recipient in enumerate(recipients):
            countdown = i * delay_seconds
            if campaign.template:
                content = {
                    'components': _build_template_components(
                        campaign.message_content,
                        recipient.variables,
                    )
                }
                msg_type = 'template'
            else:
                content = {
                    'text': _personalize_message(
                        campaign.message_content.get('text', ''),
                        recipient.variables,
                    )
                }
                msg_type = 'text'

            send_campaign_message.apply_async(
                args=[
                    str(campaign.account_id),
                    str(recipient.id),
                    str(campaign_id),
                    msg_type,
                    content,
                ],
                countdown=countdown,
            )
            scheduled += 1

        return {'status': 'success', 'scheduled': scheduled}
    except Campaign.DoesNotExist:
        return {'status': 'error', 'reason': 'not_found'}
    except Exception:
        logger.exception("Error scheduling campaign messages")
        raise


def _build_template_components(content: dict, variables: dict) -> list:
    """Build template components with recipient variables."""
    components = (content or {}).get('components', [])
    variables = variables or {}

    for component in components:
        params = component.get('parameters', [])
        for param in params:
            if param.get('type') == 'text' and 'variable' in param:
                variable_name = param['variable']
                param['text'] = variables.get(variable_name, param.get('text', ''))
    return components


def _personalize_message(text: str, variables: dict) -> str:
    """Interpolate variable placeholders in text."""
    result = text or ''
    for key, value in (variables or {}).items():
        result = result.replace(f'{{{{{key}}}}}', str(value))
    return result
