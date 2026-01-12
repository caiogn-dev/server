"""
WebSocket URL routing for stores app.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Store orders (for dashboard)
    re_path(
        r'ws/stores/(?P<store_slug>[\w-]+)/orders/$',
        consumers.StoreOrdersConsumer.as_asgi()
    ),
    
    # Customer order tracking
    re_path(
        r'ws/orders/(?P<order_id>[0-9a-f-]+)/$',
        consumers.CustomerOrderConsumer.as_asgi()
    ),
]
