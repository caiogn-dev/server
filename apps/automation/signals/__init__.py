"""
Pastita Signals - Sinais Django para automação.
"""
from .order_signals import (
    order_status_changed,
    notify_order_status,
    send_status_notification_task,
    get_status_message,
    send_whatsapp_notification,
    DEFAULT_STATUS_MESSAGES,
)

__all__ = [
    'order_status_changed',
    'notify_order_status',
    'send_status_notification_task',
    'get_status_message',
    'send_whatsapp_notification',
    'DEFAULT_STATUS_MESSAGES',
]
