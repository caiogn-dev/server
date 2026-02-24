"""
Order Notification Tasks - Celery tasks for sending order status notifications
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_order_status_notification(self, order_id: str, status: str):
    """
    Send WhatsApp notification for order status change.
    
    Args:
        order_id: UUID of the order
        status: New order status
    """
    try:
        from apps.stores.models import StoreOrder
        from apps.automation.models import CompanyProfile
        from apps.automation.services.pastita_langgraph_orchestrator import PastitaLangGraphOrchestrator
        
        # Get order
        order = StoreOrder.objects.filter(id=order_id).first()
        if not order:
            logger.error(f"Order {order_id} not found")
            return
        
        # Get company
        company = CompanyProfile.objects.filter(store=order.store).first()
        if not company:
            logger.warning(f"No company found for store {order.store_id}")
            return
        
        # Check if notifications are enabled
        if not company.order_status_notification_enabled:
            logger.info(f"Order status notifications disabled for company {company.id}")
            return
        
        # Create orchestrator and send notification
        orchestrator = PastitaLangGraphOrchestrator(
            store=order.store,
            company=company
        )
        
        orchestrator.send_order_status_notification(order, status)
        
        logger.info(f"Order status notification sent: {order.order_number} - {status}")
        
    except Exception as e:
        logger.exception(f"Error sending order status notification: {e}")
        # Retry with exponential backoff
        retry_count = self.request.retries
        if retry_count < 3:
            raise self.retry(countdown=60 * (2 ** retry_count))
