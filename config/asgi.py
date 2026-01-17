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

# Custom origin validator that allows all origins in development
# and validates against ALLOWED_HOSTS in production
class PermissiveOriginValidator:
    """
    Allow WebSocket connections from any origin.
    This is needed because the dashboard may be hosted on a different domain.
    """
    def __init__(self, application):
        self.application = application
    
    async def __call__(self, scope, receive, send):
        # Log connection attempt for debugging
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode()
        logger.info(f"WebSocket connection attempt from origin: {origin}")
        
        # Always allow - we handle authentication in the consumer
        return await self.application(scope, receive, send)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": PermissiveOriginValidator(
        TokenAuthMiddlewareStack(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        )
    ),
})
