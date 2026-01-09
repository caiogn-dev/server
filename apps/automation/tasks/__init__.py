"""
Celery tasks for automation.
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .scheduled import (
    send_scheduled_message,
    process_scheduled_messages,
    generate_report,
    process_scheduled_reports,
    cleanup_old_reports
)

logger = logging.getLogger(__name__)

__all__ = [
    'send_abandoned_cart_notification',
    'send_pix_reminder',
    'check_abandoned_carts',
    'check_pending_pix_payments',
    'cleanup_expired_sessions',
    'process_incoming_message',
    'send_scheduled_message',
    'process_scheduled_messages',
    'generate_report',
    'process_scheduled_reports',
    'cleanup_old_reports',
]


@shared_task(bind=True, max_retries=3)
def send_abandoned_cart_notification(self, session_id: str):
    """Send abandoned cart notification."""
    from ..models import CustomerSession, AutoMessage
    from ..services import AutomationService
    
    try:
        session = CustomerSession.objects.select_related('company').get(
            id=session_id,
            is_active=True
        )
        
        # Check if session is still abandoned (not completed)
        if session.status not in [
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CART_ABANDONED
        ]:
            logger.info(f"Session {session_id} no longer abandoned, skipping notification")
            return
        
        # Check if notification was already sent
        if session.was_notification_sent(AutoMessage.EventType.CART_ABANDONED):
            logger.info(f"Abandoned cart notification already sent for session {session_id}")
            return
        
        service = AutomationService()
        service._send_notification(
            session.company,
            session,
            AutoMessage.EventType.CART_ABANDONED,
            {}
        )
        
        logger.info(f"Abandoned cart notification sent for session {session_id}")
        
    except CustomerSession.DoesNotExist:
        logger.warning(f"Session not found: {session_id}")
    except Exception as e:
        logger.error(f"Error sending abandoned cart notification: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_pix_reminder(self, session_id: str):
    """Send PIX payment reminder."""
    from ..models import CustomerSession, AutoMessage
    from ..services import AutomationService
    
    try:
        session = CustomerSession.objects.select_related('company').get(
            id=session_id,
            is_active=True
        )
        
        # Check if payment is still pending
        if session.status != CustomerSession.SessionStatus.PAYMENT_PENDING:
            logger.info(f"Session {session_id} no longer pending payment")
            return
        
        # Check if PIX expired
        if session.pix_expires_at and session.pix_expires_at < timezone.now():
            # Send expired notification instead
            service = AutomationService()
            service._send_notification(
                session.company,
                session,
                AutoMessage.EventType.PIX_EXPIRED,
                {}
            )
            return
        
        # Check if reminder was already sent
        if session.was_notification_sent(AutoMessage.EventType.PIX_REMINDER):
            return
        
        service = AutomationService()
        service._send_notification(
            session.company,
            session,
            AutoMessage.EventType.PIX_REMINDER,
            {
                'amount': str(session.cart_total),
            }
        )
        
        logger.info(f"PIX reminder sent for session {session_id}")
        
    except CustomerSession.DoesNotExist:
        logger.warning(f"Session not found: {session_id}")
    except Exception as e:
        logger.error(f"Error sending PIX reminder: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@shared_task
def check_abandoned_carts():
    """
    Periodic task to check for abandoned carts.
    Run every 5 minutes.
    """
    from ..models import CustomerSession, CompanyProfile
    
    # Find sessions with carts created more than X minutes ago
    # that haven't progressed to checkout
    
    profiles = CompanyProfile.objects.filter(
        is_active=True,
        abandoned_cart_notification=True
    )
    
    for profile in profiles:
        threshold = timezone.now() - timedelta(minutes=profile.abandoned_cart_delay_minutes)
        
        abandoned_sessions = CustomerSession.objects.filter(
            company=profile,
            status=CustomerSession.SessionStatus.CART_CREATED,
            cart_created_at__lt=threshold,
            is_active=True
        )
        
        for session in abandoned_sessions:
            if not session.was_notification_sent('cart_abandoned'):
                send_abandoned_cart_notification.delay(str(session.id))
                session.status = CustomerSession.SessionStatus.CART_ABANDONED
                session.save(update_fields=['status'])


@shared_task
def check_pending_pix_payments():
    """
    Periodic task to check for pending PIX payments.
    Run every 10 minutes.
    """
    from ..models import CustomerSession
    
    # Find sessions with pending PIX that are about to expire
    threshold = timezone.now() + timedelta(minutes=30)
    
    pending_sessions = CustomerSession.objects.filter(
        status=CustomerSession.SessionStatus.PAYMENT_PENDING,
        pix_expires_at__lt=threshold,
        pix_expires_at__gt=timezone.now(),
        is_active=True
    )
    
    for session in pending_sessions:
        if not session.was_notification_sent('pix_reminder'):
            send_pix_reminder.delay(str(session.id))


@shared_task
def cleanup_expired_sessions():
    """
    Periodic task to cleanup expired sessions.
    Run daily.
    """
    from ..models import CustomerSession
    
    # Mark old inactive sessions as expired
    threshold = timezone.now() - timedelta(days=7)
    
    CustomerSession.objects.filter(
        last_activity_at__lt=threshold,
        status__in=[
            CustomerSession.SessionStatus.ACTIVE,
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CART_ABANDONED,
        ]
    ).update(status=CustomerSession.SessionStatus.EXPIRED)


@shared_task(bind=True, max_retries=3)
def process_incoming_message(self, account_id: str, from_number: str, message_text: str, message_type: str = 'text', message_data: dict = None):
    """Process incoming message and send auto-response."""
    from ..services import AutomationService
    
    try:
        service = AutomationService()
        response = service.handle_incoming_message(
            account_id=account_id,
            from_number=from_number,
            message_text=message_text,
            message_type=message_type,
            message_data=message_data
        )
        
        if response:
            logger.info(f"Auto-response sent to {from_number}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing incoming message: {str(e)}")
        raise self.retry(exc=e, countdown=30)
