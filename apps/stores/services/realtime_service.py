"""
Helpers for broadcasting store order realtime events.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

SUPPORTED_ORDER_EVENTS = {
    'order.created',
    'order.updated',
    'order.paid',
    'order.cancelled',
}

ORDER_EVENT_ALIASES = {
    'order.update': 'order.updated',
    'order.status_changed': 'order.updated',
    'order.shipped': 'order.updated',
    'order.processing': 'order.updated',
    'order.delivered': 'order.updated',
    'order.completed': 'order.updated',
}


def resolve_default_order_event_type(order) -> str:
    """Infer the most appropriate event when the caller does not specify one."""
    if getattr(order, 'status', None) == 'cancelled':
        return 'order.cancelled'

    if getattr(order, 'payment_status', None) == 'paid':
        return 'order.paid'

    return 'order.updated'


def normalize_order_event_type(event_type: str | None) -> str:
    """Map legacy or unsupported order event names to the supported contract."""
    if not event_type:
        return 'order.updated'

    if event_type in SUPPORTED_ORDER_EVENTS:
        return event_type

    return ORDER_EVENT_ALIASES.get(event_type, 'order.updated')


def broadcast_order_event(order, event_type: str | None = None, reason: str | None = None) -> bool:
    """Send an order event to the store WebSocket group."""
    normalized_event_type = (
        resolve_default_order_event_type(order)
        if event_type is None
        else normalize_order_event_type(event_type)
    )

    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning(
                "Skipping realtime broadcast for order %s: channel layer unavailable",
                order.order_number,
            )
            return False

        payload = {
            'type': normalized_event_type,
            'order_id': str(order.id),
            'order_number': order.order_number,
            'status': getattr(order, 'status', None),
            'payment_status': getattr(order, 'payment_status', None),
            'updated_at': order.updated_at.isoformat() if getattr(order, 'updated_at', None) else None,
            'created_at': order.created_at.isoformat() if getattr(order, 'created_at', None) else None,
            'customer_name': getattr(order, 'customer_name', None),
            'total': str(order.total) if getattr(order, 'total', None) is not None else None,
            'paid_at': order.paid_at.isoformat() if getattr(order, 'paid_at', None) else None,
            'cancelled_at': order.cancelled_at.isoformat() if getattr(order, 'cancelled_at', None) else None,
        }
        if reason:
            payload['reason'] = reason

        async_to_sync(channel_layer.group_send)(
            f"store_{order.store.slug}_orders",
            {key: value for key, value in payload.items() if value is not None},
        )

        logger.info(
            "Broadcasted realtime event %s for order %s",
            normalized_event_type,
            order.order_number,
        )
        return True
    except Exception:
        logger.exception("Error broadcasting realtime event for order %s", order.order_number)
        return False
