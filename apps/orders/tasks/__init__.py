"""
Order Celery tasks.
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task
def check_pending_orders():
    """Check and notify about pending orders."""
    from ..models import Order
    
    pending_orders = Order.objects.filter(
        status__in=[Order.OrderStatus.PENDING, Order.OrderStatus.AWAITING_PAYMENT],
        is_active=True,
        created_at__lt=timezone.now() - timedelta(hours=24)
    )
    
    for order in pending_orders:
        logger.info(f"Pending order reminder: {order.order_number}")


@shared_task
def cleanup_abandoned_orders(days: int = 7):
    """Cancel abandoned orders."""
    from ..models import Order
    from ..services import OrderService
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    abandoned_orders = Order.objects.filter(
        status=Order.OrderStatus.PENDING,
        is_active=True,
        created_at__lt=cutoff_date
    )
    
    service = OrderService()
    
    for order in abandoned_orders:
        try:
            service.cancel_order(
                str(order.id),
                reason="Order abandoned - no activity for 7 days"
            )
            logger.info(f"Abandoned order cancelled: {order.order_number}")
        except Exception as e:
            logger.error(f"Failed to cancel abandoned order {order.order_number}: {str(e)}")
