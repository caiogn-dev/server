"""
Celery tasks for Orders app.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.orders.tasks.check_store_abandoned_carts')
def check_store_abandoned_carts():
    """
    Check for abandoned StoreCart and trigger email notifications.
    Runs every 5 minutes via Celery Beat.
    """
    from apps.stores.models import StoreCart
    from apps.marketing.services.email_automation_service import email_automation_service
    
    # Find carts that:
    # - Have items
    # - Were updated more than 30 minutes ago
    # - Are still active (not converted to order)
    # - Have a user with email
    cutoff_time = timezone.now() - timedelta(minutes=30)
    
    abandoned_carts = StoreCart.objects.filter(
        is_active=True,
        updated_at__lt=cutoff_time,
        user__isnull=False,
        user__email__isnull=False,
    ).exclude(
        user__email=''
    ).select_related('store', 'user').prefetch_related('items')
    
    sent_count = 0
    for cart in abandoned_carts:
        # Skip empty carts
        if cart.items.count() == 0:
            continue
        
        # Check if we already sent notification (stored in metadata)
        if cart.metadata.get('abandoned_email_sent'):
            continue
        
        # Trigger email automation
        try:
            result = email_automation_service.trigger(
                store_id=str(cart.store.id),
                trigger_type='cart_abandoned',
                recipient_email=cart.user.email,
                recipient_name=cart.user.get_full_name() or cart.user.email.split('@')[0],
                context={
                    'cart_total': f'{cart.subtotal:.2f}',
                    'item_count': cart.item_count,
                }
            )
            
            if result.get('success') or result.get('scheduled'):
                # Mark as sent
                cart.metadata['abandoned_email_sent'] = True
                cart.metadata['abandoned_email_sent_at'] = timezone.now().isoformat()
                cart.save(update_fields=['metadata'])
                sent_count += 1
                logger.info(f"Abandoned cart email triggered for {cart.user.email}")
            
        except Exception as e:
            logger.error(f"Failed to send abandoned cart email for cart {cart.id}: {e}")
    
    logger.info(f"Checked abandoned carts: {sent_count} emails triggered")
    return sent_count


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
