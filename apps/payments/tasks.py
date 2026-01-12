"""
Celery tasks for Payments app.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.payments.tasks.check_expired_payments')
def check_expired_payments():
    """
    Check for expired payments and update their status.
    """
    from .models import Payment
    
    now = timezone.now()
    expired_payments = Payment.objects.filter(
        status='pending',
        expires_at__lt=now
    )
    
    count = expired_payments.update(status='failed')
    logger.info(f"Marked {count} payments as expired")
    return count


@shared_task(name='apps.payments.tasks.process_payment_webhook')
def process_payment_webhook(webhook_event_id: str):
    """
    Process a payment webhook event asynchronously.
    """
    from .models import PaymentWebhookEvent
    from .services.payment_service import PaymentService
    
    try:
        event = PaymentWebhookEvent.objects.get(id=webhook_event_id)
        if event.processed:
            logger.info(f"Payment webhook {webhook_event_id} already processed")
            return
            
        service = PaymentService()
        service.process_webhook(event)
        
        event.processed = True
        event.save(update_fields=['processed'])
        
        logger.info(f"Processed payment webhook: {webhook_event_id}")
        
    except PaymentWebhookEvent.DoesNotExist:
        logger.error(f"Payment webhook event not found: {webhook_event_id}")
    except Exception as e:
        logger.error(f"Error processing payment webhook: {e}")
        raise


@shared_task(name='apps.payments.tasks.send_payment_reminder')
def send_payment_reminder(payment_id: str):
    """
    Send payment reminder for pending payments.
    """
    from .models import Payment
    from apps.notifications.services.notification_service import NotificationService
    
    try:
        payment = Payment.objects.get(id=payment_id)
        
        if payment.status != 'pending':
            logger.info(f"Payment {payment_id} is no longer pending")
            return
            
        service = NotificationService()
        service.send_payment_reminder(payment)
        
        logger.info(f"Sent payment reminder for payment {payment_id}")
        
    except Payment.DoesNotExist:
        logger.error(f"Payment not found: {payment_id}")
    except Exception as e:
        logger.error(f"Error sending payment reminder: {e}")
        raise


@shared_task(name='apps.payments.tasks.sync_payment_status')
def sync_payment_status(payment_id: str):
    """
    Sync payment status with payment gateway.
    """
    from .models import Payment
    from .services.payment_service import PaymentService
    
    try:
        payment = Payment.objects.get(id=payment_id)
        service = PaymentService()
        
        updated = service.sync_status(payment)
        
        if updated:
            logger.info(f"Updated payment {payment_id} status to {payment.status}")
        else:
            logger.info(f"Payment {payment_id} status unchanged")
            
        return updated
        
    except Payment.DoesNotExist:
        logger.error(f"Payment not found: {payment_id}")
    except Exception as e:
        logger.error(f"Error syncing payment status: {e}")
        raise
