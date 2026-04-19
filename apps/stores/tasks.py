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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_order_to_toca_delivery(self, order_id: str):
    """
    Create a corrida in Toca Delivery for a confirmed delivery order.

    Called automatically when StoreOrder.status becomes 'confirmed'
    and the store has Toca Delivery configured.
    """
    from apps.stores.models import StoreOrder
    from apps.stores.services.delivery_provider import get_delivery_provider, TocaDeliveryProvider
    from apps.stores.services.delivery_provider.base import DeliveryProviderError

    try:
        order = StoreOrder.objects.select_related('store').get(id=order_id)
    except StoreOrder.DoesNotExist:
        logger.warning('dispatch_order_to_toca_delivery: order %s not found', order_id)
        return

    if order.delivery_method != 'delivery':
        logger.info('dispatch_order_to_toca_delivery: order %s is pickup, skipping', order_id)
        return

    if order.external_delivery_id:
        logger.info('dispatch_order_to_toca_delivery: order %s already dispatched (%s)', order_id, order.external_delivery_id)
        return

    store = order.store
    provider = get_delivery_provider(store)

    if not isinstance(provider, TocaDeliveryProvider):
        return

    try:
        result = provider.create(store, order)
        StoreOrder.objects.filter(id=order_id).update(
            external_delivery_provider='toca',
            external_delivery_id=result.external_id,
            external_delivery_code=result.external_code,
            external_delivery_status=result.external_status,
            external_delivery_url=result.tracking_url or '',
        )
        logger.info(
            'dispatch_order_to_toca_delivery: order %s dispatched as corrida %s (%s)',
            order.order_number, result.external_code, result.external_id,
        )
    except DeliveryProviderError as exc:
        logger.error('dispatch_order_to_toca_delivery: failed for order %s: %s', order_id, exc)
        raise self.retry(exc=exc)


@shared_task
def sync_toca_delivery_statuses():
    """
    Periodic task (Celery Beat, every 60s) that polls Toca Delivery for status
    updates on all active external deliveries and applies order status transitions.

    Only runs when TOCA_DELIVERY_ENABLED=True.
    """
    from django.conf import settings
    from apps.stores.models import StoreOrder
    from apps.stores.services.delivery_provider import TocaDeliveryProvider

    if not getattr(settings, 'TOCA_DELIVERY_ENABLED', False):
        return

    active = StoreOrder.objects.filter(
        external_delivery_provider='toca',
        external_delivery_id__gt='',
    ).exclude(
        external_delivery_status__in=['entregue', 'cancelada'],
    ).exclude(
        status__in=['delivered', 'cancelled', 'completed'],
    ).values('id', 'external_delivery_id', 'external_delivery_status', 'status')

    if not active:
        return

    provider = TocaDeliveryProvider()
    updated = 0

    for row in active:
        external_id = row['external_delivery_id']
        try:
            new_ext_status = provider.get_status(external_id)
            if not new_ext_status or new_ext_status == row['external_delivery_status']:
                continue

            order_status = provider.map_status_to_order(new_ext_status)
            update_fields = {'external_delivery_status': new_ext_status}

            if order_status and order_status != row['status']:
                update_fields['status'] = order_status

                if order_status == 'out_for_delivery':
                    from django.utils import timezone
                    update_fields['out_for_delivery_at'] = timezone.now()
                elif order_status == 'delivered':
                    from django.utils import timezone
                    update_fields['delivered_at'] = timezone.now()

            StoreOrder.objects.filter(id=row['id']).update(**update_fields)
            updated += 1
        except Exception as exc:
            logger.warning('sync_toca_delivery_statuses: error for corrida %s: %s', external_id, exc)

    if updated:
        logger.info('sync_toca_delivery_statuses: updated %d orders', updated)