"""
ASGI config for WhatsApp Business Platform.
Supports HTTP and WebSocket protocols.
"""
import os
import logging
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from apps.core.middleware import TokenAuthMiddlewareStack
from apps.core.routing import websocket_urlpatterns

logger = logging.getLogger(__name__)

class CORSOriginValidator:
    """
    Validate WebSocket connection origins against CORS_ALLOWED_ORIGINS.
    Falls back to permissive in DEBUG mode to ease local development.
    Authentication is still enforced independently by TokenAuthMiddleware.
    """
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        from django.conf import settings

        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode()

        if not origin:
            # No Origin header — likely a server-side or same-origin connection
            return await self.application(scope, receive, send)

        if settings.DEBUG:
            logger.info(f"WebSocket connection (DEBUG, origin accepted): {origin}")
            return await self.application(scope, receive, send)

        allowed = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        if origin in allowed:
            return await self.application(scope, receive, send)

        logger.warning(f"WebSocket connection rejected — origin not in CORS_ALLOWED_ORIGINS: {origin}")
        await send({'type': 'websocket.close', 'code': 4403})


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": CORSOriginValidator(
        TokenAuthMiddlewareStack(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        )
    ),
})
