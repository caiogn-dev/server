"""
WebSocket routing para messaging_v2.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Conversas em tempo real
    re_path(r'ws/stores/(?P<store_slug>[^/]+)/conversations/$', 
            consumers.ConversationConsumer.as_asgi()),
    
    # Pedidos em tempo real
    re_path(r'ws/stores/(?P<store_slug>[^/]+)/orders/$', 
            consumers.OrderConsumer.as_asgi()),
    
    # Dashboard em tempo real
    re_path(r'ws/stores/(?P<store_slug>[^/]+)/dashboard/$', 
            consumers.DashboardConsumer.as_asgi()),
    re_path(r'ws/dashboard/$', 
            consumers.DashboardConsumer.as_asgi()),
]
