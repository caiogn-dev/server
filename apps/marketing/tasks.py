"""
Celery tasks for Marketing app.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.marketing.tasks.process_scheduled_automations')
def process_scheduled_automations():
    """
    Process scheduled email automations.
    Runs every minute via Celery Beat.
    """
    from apps.marketing.services.email_automation_service import email_automation_service
    
    try:
        result = email_automation_service.process_scheduled()
        logger.info(f"Processed scheduled automations: {result}")
        return result
    except Exception as e:
        logger.error(f"Error processing scheduled automations: {e}")
        raise


@shared_task(name='apps.marketing.tasks.send_campaign')
def send_campaign(campaign_id: str):
    """
    Send an email campaign asynchronously.
    """
    from apps.marketing.services import email_marketing_service
    
    try:
        result = email_marketing_service.send_campaign(campaign_id)
        logger.info(f"Campaign {campaign_id} sent: {result}")
        return result
    except Exception as e:
        logger.error(f"Error sending campaign {campaign_id}: {e}")
        raise


@shared_task(name='apps.marketing.tasks.send_automation_email')
def send_automation_email(automation_id: str, recipient_email: str, recipient_name: str, context: dict = None):
    """
    Send a single automation email asynchronously.
    """
    from apps.marketing.models import EmailAutomation, EmailAutomationLog
    from apps.marketing.services.email_automation_service import email_automation_service
    
    try:
        automation = EmailAutomation.objects.get(id=automation_id)
        
        # Create log entry
        log = EmailAutomationLog.objects.create(
            automation=automation,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            trigger_data=context or {},
            status='pending'
        )
        
        # Send email
        result = email_automation_service._send_automation_email(automation, log, context or {})
        logger.info(f"Automation email sent to {recipient_email}: {result}")
        return result
        
    except EmailAutomation.DoesNotExist:
        logger.error(f"Automation not found: {automation_id}")
        return {'success': False, 'error': 'Automation not found'}
    except Exception as e:
        logger.error(f"Error sending automation email: {e}")
        raise
