"""
Payment Celery tasks.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_payment_webhook(self, event_id: str):
    """Process a payment webhook event asynchronously."""
    from ..services import PaymentService
    
    try:
        service = PaymentService()
        service.handle_webhook_event(event_id)
        logger.info(f"Payment webhook processed: {event_id}")
        
    except Exception as e:
        logger.error(f"Error processing payment webhook {event_id}: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def check_expired_payments():
    """Check and expire pending payments."""
    from django.utils import timezone
    from ..models import Payment
    from ..services import PaymentService
    
    expired_payments = Payment.objects.filter(
        status=Payment.PaymentStatus.PENDING,
        expires_at__lt=timezone.now(),
        is_active=True
    )
    
    service = PaymentService()
    
    for payment in expired_payments:
        try:
            service.fail_payment(
                str(payment.id),
                'expired',
                'Payment expired'
            )
            logger.info(f"Payment expired: {payment.payment_id}")
        except Exception as e:
            logger.error(f"Failed to expire payment {payment.payment_id}: {str(e)}")
