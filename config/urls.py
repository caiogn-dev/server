"""
URL configuration for Pastita E-commerce Platform.

Main API endpoints:
- /api/v1/stores/{store_slug}/ - Unified store API (catalog, cart, checkout, etc.)
- /api/v1/auth/ - Authentication (login, register, logout)
- /api/v1/users/ - User profile management

Admin/Dashboard endpoints:
- /api/v1/stores/ - Store management (admin)
- /admin/ - Django admin

Webhooks:
- /webhooks/v1/{provider}/ - Unified webhook endpoints
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from apps.core.dashboard_views import DashboardStatsView
from apps.core.sse_views import (
    OrderSSEView, 
    WhatsAppSSEView, 
    WebSocketHealthCheckView
)

from apps.webhooks.handlers.whatsapp_handler import WhatsAppHandler
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def whatsapp_verification_view(request):
    """Direct WhatsApp verification endpoint for Meta."""
    handler = WhatsAppHandler()
    return handler.handle_verification(request)

urlpatterns = [
    path('admin/', admin.site.urls),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API v1 - Unified
    path('api/v1/', include([
        # Core (auth, users, csrf)
        path('', include('apps.core.urls')),
        path('auth/', include('apps.core.auth.urls')),

        # Unified Store API
        path('stores/', include('apps.stores.urls')),

        # Dashboard/Admin APIs
        path('notifications/', include('apps.notifications.urls')),

        # WhatsApp, Instagram & Automation (Unified)
        path('whatsapp/', include('apps.whatsapp.urls')),
        path('instagram/', include('apps.instagram.urls')),
        path('messaging/', include('apps.messaging.urls')),
        path('conversations/', include('apps.conversations.urls')),
        path('automation/', include('apps.automation.urls')),
        path('handover/', include('apps.handover.urls')),
        path('users/', include('apps.users.urls')),
        path('agents/', include('apps.agents.urls')),

        # Marketing & Audit
        path('marketing/', include('apps.marketing.urls')),
        path('campaigns/', include('apps.campaigns.urls')),
        path('audit/', include('apps.audit.urls')),
    ])),

    path('api/v1/core/dashboard-stats/', DashboardStatsView.as_view(), name='core-dashboard-stats'),

    # SSE (Server-Sent Events) - Fallback for WebSocket
    path('api/sse/', include([
        path('orders/', OrderSSEView.as_view(), name='sse_orders'),
        path('whatsapp/', WhatsAppSSEView.as_view(), name='sse_whatsapp'),
        path('health/', WebSocketHealthCheckView.as_view(), name='sse_health'),
    ])),

    # Unified Webhooks v1 (centralized handlers)
    # Meta WhatsApp API sends webhooks WITHOUT trailing slash for verification
    path('webhooks/v1/', include('apps.webhooks.urls')),
    
    # Direct WhatsApp verification endpoint (no trailing slash required by Meta)
    path('webhooks/v1/whatsapp', whatsapp_verification_view, name='whatsapp_webhook_no_slash'),
    path('webhooks/v1/whatsapp/', include('apps.webhooks.urls')),  # With trailing slash for regular webhooks
]

# Serve media files when not using S3
if not getattr(settings, 'USE_S3', False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
