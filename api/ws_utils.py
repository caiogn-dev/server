import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def broadcast_admin_event(event_type: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("Channel layer not configured for admin events.")
        return
    async_to_sync(channel_layer.group_send)(
        "admin_updates",
        {
            "type": "admin.event",
            "event": event_type,
            "payload": payload,
        },
    )
