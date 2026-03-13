"""
ASGI config for WhatsApp Business Platform.
Supports HTTP and WebSocket protocols.
"""
import os
import logging
from django.core.asgi import get_asgi_application
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator
from apps.core.middleware import TokenAuthMiddlewareStack
from apps.core.routing import websocket_urlpatterns

logger = logging.getLogger(__name__)


def _build_allowed_ws_origins():
    """Compose websocket allowed origins from Django/CORS settings."""
    origins = set()

    for attr in ('WEBSOCKET_ALLOWED_ORIGINS', 'CORS_ALLOWED_ORIGINS', 'CSRF_TRUSTED_ORIGINS'):
        for origin in getattr(settings, attr, []) or []:
            origin = str(origin).strip().rstrip('/')
            if origin:
                origins.add(origin)

    for host in getattr(settings, 'ALLOWED_HOSTS', []) or []:
        host = str(host).strip()
        if not host or host == '*':
            continue
        if host.startswith('.'):
            host = host[1:]
        # ALLOWED_HOSTS entries should not include ports, but normalize if they do.
        if ':' in host:
            host = host.split(':', 1)[0]
        origins.add(f"http://{host}")
        origins.add(f"https://{host}")

    return sorted(origins)


def _allow_all_ws_origins() -> bool:
    raw_flag = str(getattr(settings, 'WEBSOCKET_ALLOW_ALL_ORIGINS', '')).strip().lower()
    return bool(settings.DEBUG) or raw_flag in {'1', 'true', 'yes', 'on'}


websocket_stack = TokenAuthMiddlewareStack(
    AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    )
)

if _allow_all_ws_origins():
    logger.warning("WebSocket origin validation relaxed (development mode).")
else:
    allowed_origins = _build_allowed_ws_origins()
    if allowed_origins:
        websocket_stack = OriginValidator(websocket_stack, allowed_origins)
    websocket_stack = AllowedHostsOriginValidator(websocket_stack)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": websocket_stack,
})
