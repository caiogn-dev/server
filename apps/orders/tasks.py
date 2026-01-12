"""
Celery tasks for Orders app.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.orders.tasks.check_pending_orders')
def check_pending_orders():
    """
    Check for orders that have been pending for too long.
    """
    from .models import Order
    
    # Find orders pending for more than 24 hours
    cutoff_time = timezone.now() - timedelta(hours=24)
    pending_orders = Order.objects.filter(
        status='pending',
        created_at__lt=cutoff_time
    )
    
    count = pending_orders.count()
    logger.info(f"Found {count} orders pending for more than 24 hours")
    
    # Could send notifications or auto-cancel here
    return count


@shared_task(name='apps.orders.tasks.send_order_notification')
def send_order_notification(order_id: str, notification_type: str):
    """
    Send order notification asynchronously.
    """
    from .models import Order
    from apps.notifications.services.notification_service import NotificationService
    
    try:
        order = Order.objects.get(id=order_id)
        service = NotificationService()
        
        if notification_type == 'confirmation':
            service.send_order_confirmation(order)
        elif notification_type == 'shipped':
            service.send_order_shipped(order)
        elif notification_type == 'delivered':
            service.send_order_delivered(order)
        elif notification_type == 'cancelled':
            service.send_order_cancelled(order)
        else:
            logger.warning(f"Unknown notification type: {notification_type}")
            return
            
        logger.info(f"Sent {notification_type} notification for order {order.order_number}")
        
    except Order.DoesNotExist:
        logger.error(f"Order not found: {order_id}")
    except Exception as e:
        logger.error(f"Error sending order notification: {e}")
        raise


@shared_task(name='apps.orders.tasks.update_order_status')
def update_order_status(order_id: str, new_status: str, actor_id: int = None):
    """
    Update order status asynchronously.
    """
    from .models import Order
    from .services.order_service import OrderService
    
    try:
        order = Order.objects.get(id=order_id)
        service = OrderService()
        
        service.update_status(order, new_status, actor_id)
        logger.info(f"Updated order {order.order_number} status to {new_status}")
        
    except Order.DoesNotExist:
        logger.error(f"Order not found: {order_id}")
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        raise


@shared_task(name='apps.orders.tasks.generate_order_report')
def generate_order_report(start_date: str, end_date: str, format: str = 'csv'):
    """
    Generate order report asynchronously.
    """
    from .models import Order
    from django.db.models import Sum, Count
    import csv
    import io
    
    try:
        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        stats = orders.aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total'),
        )
        
        logger.info(f"Generated report: {stats['total_orders']} orders, R${stats['total_revenue'] or 0:.2f} revenue")
        return stats
        
    except Exception as e:
        logger.error(f"Error generating order report: {e}")
        raise
