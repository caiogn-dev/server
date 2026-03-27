"""
Celery tasks for the stores app.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def notify_new_order_push(self, order_id: str):
    """
    Send a Web Push notification to all active push subscriptions
    of the store owner and staff when a new order is placed.
    """
    try:
        from apps.stores.models import StoreOrder
        from apps.notifications.models import Notification, PushSubscription
        from apps.notifications.services import NotificationService

        try:
            order = StoreOrder.objects.select_related('store__owner').get(id=order_id)
        except StoreOrder.DoesNotExist:
            logger.warning(f"notify_new_order_push: order {order_id} not found")
            return

        store = order.store

        # Collect all users that should receive the notification
        recipients = set()
        if store.owner:
            recipients.add(store.owner)
        for staff_user in store.staff.all():
            recipients.add(staff_user)

        if not recipients:
            return

        service = NotificationService()
        title = f"Novo pedido #{order.order_number}"
        message = (
            f"{order.customer_name or 'Cliente'} — "
            f"R$ {order.total:.2f}"
        )
        data = {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'store_id': str(store.id),
            'url': f'/orders/{order.id}',
        }

        for user in recipients:
            notification = service.create_notification(
                title=title,
                message=message,
                notification_type=Notification.NotificationType.ORDER,
                priority=Notification.Priority.HIGH,
                user=user,
                data=data,
                related_object_type='order',
                related_object_id=str(order.id),
                send_push=True,
                send_realtime=True,
            )

        logger.info(f"New-order push sent for order {order.order_number} to {len(recipients)} user(s)")

    except Exception as exc:
        logger.error(f"notify_new_order_push failed: {exc}")
        raise self.retry(exc=exc)