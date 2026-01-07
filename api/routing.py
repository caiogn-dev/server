from django.urls import re_path
from .consumers import AdminUpdatesConsumer

websocket_urlpatterns = [
    re_path(r"^ws/admin/$", AdminUpdatesConsumer.as_asgi()),
]
