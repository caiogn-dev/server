"""
ASGI config for server project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.settings')

from django.core.asgi import get_asgi_application
from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator

from api.routing import websocket_urlpatterns
from api.ws_auth import TokenAuthMiddleware

django_asgi_app = get_asgi_application()

allowed_origins = list(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
frontend_url = getattr(settings, "FRONTEND_URL", "")
if frontend_url and frontend_url not in allowed_origins:
    allowed_origins.append(frontend_url)
for origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
    if origin not in allowed_origins:
        allowed_origins.append(origin)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": OriginValidator(
            TokenAuthMiddleware(
                URLRouter(websocket_urlpatterns)
            ),
            allowed_origins,
        ),
    }
)
