"""
WebSocket URL routing.
"""
from django.urls import re_path
from . import consumers
from apps.automation.consumers import AutomationConsumer
from apps.payments.consumers import PaymentConsumer
from apps.orders.consumers import OrderConsumer
from apps.stores.consumers import StoreOrdersConsumer, CustomerOrderConsumer

websocket_urlpatterns = [
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<conversation_id>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/dashboard/$', consumers.DashboardConsumer.as_asgi()),
    re_path(r'ws/automation/$', AutomationConsumer.as_asgi()),
    re_path(r'ws/payments/$', PaymentConsumer.as_asgi()),
    re_path(r'ws/orders/$', OrderConsumer.as_asgi()),
    # Store-specific order updates
    re_path(r'ws/stores/(?P<store_slug>[\w-]+)/orders/$', StoreOrdersConsumer.as_asgi()),
    # Customer order tracking
    re_path(r'ws/orders/(?P<order_id>[0-9a-f-]+)/$', CustomerOrderConsumer.as_asgi()),
]
