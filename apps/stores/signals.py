"""
Django signals for the stores app.
"""
import logging
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Tracks previous status so we can detect transitions in post_save
_ORDER_PREV_STATUS = {}


@receiver(post_save, sender='stores.Store')
def invalidate_store_slug_cache(sender, instance, **kwargs):
    """Bust the storefront slug cache when a store is saved."""
    try:
        cache.delete(f'store:slug:{instance.slug}')
    except Exception as e:
        logger.warning("Failed to invalidate store cache for %s: %s", instance.slug, e)


@receiver(pre_save, sender='stores.StoreOrder')
def capture_order_previous_status(sender, instance, **kwargs):
    """Capture previous status before save for transition detection."""
    if not instance.pk:
        return

    if hasattr(instance, '_pre_save_status'):
        _ORDER_PREV_STATUS[instance.pk] = instance._pre_save_status
        return

    previous_status = (
        sender.objects
        .filter(pk=instance.pk)
        .values_list('status', flat=True)
        .first()
    )
    _ORDER_PREV_STATUS[instance.pk] = previous_status


@receiver(post_save, sender='stores.StoreOrder')
def on_order_created(sender, instance, created, **kwargs):
    """Trigger push notification when a new order is created."""
    if not created:
        return
    try:
        from apps.stores.tasks import notify_new_order_push
        order_id = str(instance.id)
        transaction.on_commit(lambda: notify_new_order_push.delay(order_id))
    except Exception as e:
        logger.error(f"on_order_created signal error: {e}")


@receiver(post_save, sender='stores.StoreOrder')
def on_order_confirmed_dispatch_toca(sender, instance, created, **kwargs):
    """
    When a delivery order becomes 'confirmed', auto-dispatch to Toca Delivery
    if the store has it enabled and the order hasn't been dispatched yet.
    """
    from django.conf import settings

    if not getattr(settings, 'TOCA_DELIVERY_ENABLED', False):
        meta = getattr(instance.store, 'metadata', None) or {}
        if meta.get('delivery_provider') != 'toca':
            return

    if instance.status != 'confirmed':
        return

    prev_status = _ORDER_PREV_STATUS.pop(instance.pk, None)
    if prev_status == 'confirmed':
        return  # status didn't change

    if instance.delivery_method != 'delivery':
        return

    if instance.external_delivery_id:
        return  # already dispatched

    try:
        from apps.stores.tasks import dispatch_order_to_toca_delivery
        order_id = str(instance.id)
        transaction.on_commit(lambda: dispatch_order_to_toca_delivery.delay(order_id))
    except Exception as exc:
        logger.error('on_order_confirmed_dispatch_toca: failed to enqueue task: %s', exc)
