"""
WebSocket URL routing.
"""
from django.urls import re_path
from . import consumers
from apps.automation.consumers import AutomationConsumer
from apps.payments.consumers import PaymentConsumer
from apps.orders.consumers import OrderConsumer

websocket_urlpatterns = [
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<conversation_id>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/dashboard/$', consumers.DashboardConsumer.as_asgi()),
    re_path(r'ws/automation/$', AutomationConsumer.as_asgi()),
    re_path(r'ws/payments/$', PaymentConsumer.as_asgi()),
    re_path(r'ws/orders/$', OrderConsumer.as_asgi()),
]
