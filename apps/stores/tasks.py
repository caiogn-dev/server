"""
Celery tasks for the stores app.
"""
import logging
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='stores.enforce_subscription_lifecycle')
def enforce_subscription_lifecycle():
    """
    Varredura diária: aplica trial→carência→suspensão e past_due→dunning→suspensão.
    Loja isenta é ignorada (decide_transition retorna 'none').
    """
    from apps.stores.models import StoreSubscription
    from apps.stores.services.subscription_lifecycle import decide_transition

    now = timezone.now()
    grace_days = getattr(settings, 'BILLING_GRACE_DAYS', 3)
    dunning_days = getattr(settings, 'BILLING_DUNNING_DAYS', 3)
    counts = {'scanned': 0, 'suspended': 0, 'grace_started': 0}

    with transaction.atomic():
        qs = (StoreSubscription.objects
              .exclude(status__in=['suspended', 'canceled'])
              .select_related('store')
              .select_for_update(skip_locked=True))
        for sub in qs:
            counts['scanned'] += 1
            store = sub.store
            t = decide_transition(
                status=sub.status,
                trial_ends_at=store.trial_ends_at,
                grace_until=sub.grace_until,
                dunning_since=sub.dunning_since,
                now=now,
                grace_days=grace_days,
                dunning_days=dunning_days,
                billing_exempt=store.billing_exempt,
            )
            if t.action == 'start_grace':
                if sub.status == 'past_due':
                    sub.dunning_since = now
                    sub.save(update_fields=['dunning_since'])
                else:
                    sub.grace_until = t.set_grace_until
                    sub.save(update_fields=['grace_until'])
                counts['grace_started'] += 1
            elif t.action == 'suspend':
                sub.status = StoreSubscription.Status.SUSPENDED
                sub.save(update_fields=['status'])
                counts['suspended'] += 1
    return counts


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


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def update_customer_stats_on_payment(self, order_id: str):
    """Update StoreCustomer stats after an order is confirmed as paid."""
    try:
        from apps.stores.models import StoreOrder, StoreCustomer
        from apps.core.services.customer_identity import CustomerIdentityService
        from django.db.models import Q

        try:
            order = StoreOrder.objects.values(
                'id', 'store_id', 'customer_phone', 'customer_id'
            ).get(id=order_id)
        except StoreOrder.DoesNotExist:
            return

        phones = set(CustomerIdentityService.phone_candidates(order['customer_phone']))
        qs = StoreCustomer.objects.filter(store_id=order['store_id'])
        if order['customer_id']:
            qs = qs.filter(
                Q(user_id=order['customer_id']) | Q(phone__in=phones) | Q(whatsapp__in=phones)
            )
        elif phones:
            qs = qs.filter(Q(phone__in=phones) | Q(whatsapp__in=phones))
        else:
            return

        for customer in qs.distinct().only('id'):
            try:
                StoreCustomer.objects.get(id=customer.id).update_stats()
            except Exception:
                logger.warning('update_customer_stats_on_payment: update_stats failed for customer %s', customer.id)
    except Exception as exc:
        logger.error('update_customer_stats_on_payment: %s', exc)
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


@shared_task(name='apps.stores.tasks.cleanup_abandoned_carts')
def cleanup_abandoned_carts():
    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('cleanup_carts', stdout=out)
    result = out.getvalue()
    logger.info('cleanup_abandoned_carts: %s', result.strip())
    return result


@shared_task(name='apps.stores.tasks.daily_database_backup')
def daily_database_backup():
    """
    Daily backup task (Celery Beat, every 24h at 02:00 AM).

    Creates a compressed PostgreSQL dump and validates database integrity.
    Keeps backups for the last 30 days.
    """
    import subprocess
    from pathlib import Path
    from django.conf import settings
    from django.core.management import call_command
    from io import StringIO

    try:
        # Run healthcheck with backup flag
        out = StringIO()
        call_command('db_healthcheck', '--backup', stdout=out)
        result = out.getvalue()
        logger.info('daily_database_backup: completed successfully\n%s', result)
        return 'success'
    except Exception as exc:
        logger.error('daily_database_backup: failed: %s', exc)
        raise


@shared_task(name='apps.stores.tasks.database_integrity_check')
def database_integrity_check():
    """
    Periodic task (Celery Beat, every 6h) that validates database integrity.

    Checks if all required stores exist and have minimum required data.
    Auto-seeds if any store is missing.
    """
    from django.core.management import call_command
    from io import StringIO

    try:
        out = StringIO()
        call_command('db_healthcheck', '--auto-seed', stdout=out)
        result = out.getvalue()
        logger.info('database_integrity_check: %s', result)
        return 'ok'
    except Exception as exc:
        logger.error('database_integrity_check: failed: %s', exc)
        # Don't retry on failure, just log it
        return f'failed: {exc}'


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_meta_purchase_event(self, order_id: str, tracking_data: dict = None):
    """Envia o evento Meta CAPI Purchase fora do request (não bloqueia o checkout).

    Os dados derivados do request (client_ip, user_agent, event_source_url, fbc/fbp)
    são pré-extraídos em tracking_data pelo caller, já que request não é serializável.
    """
    try:
        from apps.stores.models import StoreOrder
        from apps.stores.services.meta_pixel_service import send_purchase_event

        try:
            order = StoreOrder.objects.select_related('store').get(id=order_id)
        except StoreOrder.DoesNotExist:
            logger.warning('send_meta_purchase_event: order %s not found', order_id)
            return

        send_purchase_event(order, request=None, tracking_data=tracking_data or {})
    except Exception as exc:
        logger.warning('send_meta_purchase_event failed for %s: %s', order_id, exc)
        raise self.retry(exc=exc)
