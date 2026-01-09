"""
WebSocket URL routing.
"""
from django.urls import re_path
from . import consumers
from apps.automation.consumers import AutomationConsumer

websocket_urlpatterns = [
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<conversation_id>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/dashboard/$', consumers.DashboardConsumer.as_asgi()),
    re_path(r'ws/automation/$', AutomationConsumer.as_asgi()),
]
