"""
Django signals for the stores app.
"""
import logging
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
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
        cache.delete(f'catalog:{instance.slug}')
    except Exception as e:
        logger.warning("Failed to invalidate store cache for %s: %s", instance.slug, e)


@receiver(post_save, sender='stores.StoreProduct')
def invalidate_catalog_on_product_change(sender, instance, **kwargs):
    """Bust the catalog cache whenever a product is saved."""
    try:
        slug = instance.store.slug if instance.store_id else None
        if slug:
            cache.delete(f'catalog:{slug}')
    except Exception as e:
        logger.warning("Failed to invalidate catalog cache on product save: %s", e)


@receiver(post_save, sender='stores.StoreCategory')
def invalidate_catalog_on_category_change(sender, instance, **kwargs):
    """Bust the catalog cache whenever a category is saved."""
    try:
        slug = instance.store.slug if instance.store_id else None
        if slug:
            cache.delete(f'catalog:{slug}')
    except Exception as e:
        logger.warning("Failed to invalidate catalog cache on category save: %s", e)


@receiver(post_save, sender='stores.StoreCombo')
def invalidate_catalog_on_combo_change(sender, instance, **kwargs):
    """Bust the catalog cache whenever a combo is saved."""
    try:
        slug = instance.store.slug if instance.store_id else None
        if slug:
            cache.delete(f'catalog:{slug}')
    except Exception as e:
        logger.warning("Failed to invalidate catalog cache on combo save: %s", e)


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
def update_customer_stats_for_order(sender, instance, **kwargs):
    """Keep customer dashboard numbers aligned with paid orders."""
    try:
        from apps.core.services.customer_identity import CustomerIdentityService
        from apps.stores.models import StoreCustomer

        phones = set(CustomerIdentityService.phone_candidates(instance.customer_phone))
        qs = StoreCustomer.objects.filter(store=instance.store)
        if instance.customer_id:
            qs = qs.filter(user_id=instance.customer_id) | StoreCustomer.objects.filter(
                store=instance.store,
                phone__in=phones,
            ) | StoreCustomer.objects.filter(
                store=instance.store,
                whatsapp__in=phones,
            )
        elif phones:
            qs = qs.filter(Q(phone__in=phones) | Q(whatsapp__in=phones))
        else:
            qs = qs.none()

        for customer in qs.distinct():
            transaction.on_commit(lambda customer_id=customer.id: StoreCustomer.objects.get(id=customer_id).update_stats())
    except Exception as e:
        logger.error("update_customer_stats_for_order signal error: %s", e)


@receiver(post_save, sender='stores.StoreOrder')
def update_customer_sessions_for_order(sender, instance, **kwargs):
    """Keep automation customer sessions aligned with the linked order."""
    try:
        from apps.automation.models import CustomerSession

        sessions = CustomerSession.objects.filter(
            Q(order=instance) |
            Q(external_order_id=instance.order_number) |
            Q(payment_id=str(instance.id))
        ).distinct()
        if not sessions.exists():
            return

        if instance.status in {'delivered', 'completed'}:
            session_status = CustomerSession.SessionStatus.COMPLETED
        elif instance.payment_status == 'paid':
            session_status = CustomerSession.SessionStatus.PAYMENT_CONFIRMED
        elif instance.status in {'cancelled', 'failed', 'refunded'} or instance.payment_status in {'failed', 'refunded'}:
            session_status = CustomerSession.SessionStatus.EXPIRED
        elif instance.payment_status in {'pending', 'processing'}:
            session_status = CustomerSession.SessionStatus.PAYMENT_PENDING
        else:
            session_status = CustomerSession.SessionStatus.ORDER_PLACED

        update = {
            'order': instance,
            'external_order_id': instance.order_number,
            'cart_total': instance.total,
            'cart_items_count': instance.items.count(),
            'status': session_status,
        }
        if instance.customer_name:
            update['customer_name'] = instance.customer_name
        if instance.customer_email:
            update['customer_email'] = instance.customer_email

        sessions.update(**update)
    except Exception as e:
        logger.error("update_customer_sessions_for_order signal error: %s", e)


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
