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
from django.urls import path, include, re_path
from django.http import HttpResponse
from django.conf import settings
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.views.static import serve

from apps.core.dashboard_views import DashboardStatsView
from apps.core.sse_views import (
    OrderSSEView,
    WhatsAppSSEView,
    WebSocketHealthCheckView,
    SSETicketView,
)
from apps.core.auth_views import CSRFTokenView, ProfileView
from apps.stores.api.webhooks import MercadoPagoWebhookView
from apps.instagram.api.views import ig_oauth_callback

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def whatsapp_verification_view(request):
    """Direct WhatsApp verification endpoint for Meta."""
    from apps.webhooks.handlers.whatsapp_handler import WhatsAppHandler
    handler = WhatsAppHandler()
    
    # GET = verification challenge
    if request.method == 'GET':
        return handler.handle_verification(request)
    
    # POST = webhook message - delegate to dispatcher
    if request.method == 'POST':
        from apps.webhooks.dispatcher import WebhookDispatcherView
        dispatcher = WebhookDispatcherView()
        return dispatcher._handle_webhook(request, 'whatsapp')
    
    return HttpResponse("Method not allowed", status=405)

_ADMIN_URL = getattr(settings, 'ADMIN_URL', 'django-admin/')

urlpatterns = [
    path(_ADMIN_URL, admin.site.urls),

    # Pastita Panel — custom Django-rendered admin UI (multi-tenant)
    path('panel/', include('apps.panel.urls')),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API v1 - Unified
    path('api/v1/', include([
        # Compatibility aliases used by storefronts still calling legacy flat paths
        path('csrf/', CSRFTokenView.as_view(), name='csrf-token-compat'),
        path('users/profile/', ProfileView.as_view(), name='user-profile-compat'),

        # Core (auth, users, csrf)
        path('core/', include('apps.core.urls')),
        path('auth/', include('apps.core.auth.urls')),

        # Global GEO/MAPS endpoints (must be before stores/ to avoid catch-all)
        path('maps/', include('apps.stores.api.geo_maps_urls')),

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

        # Public API (no auth — storefronts: pastita-3d, ce-saladas)
        path('public/', include('apps.public_api.urls')),

        # Mobile API (Flutter) — clean stable paths, no admin conflict
        path('mobile/', include('apps.mobile_api.urls', namespace='mobile_api')),

        # Marketing & Audit
        path('marketing/', include('apps.marketing.urls')),
        path('campaigns/', include('apps.campaigns.urls')),
        path('audit/', include('apps.audit.urls')),
    ])),

    # Postado SaaS — signup + Mercado Pago webhook
    path('api/postado/', include('apps.postado.api.urls')),

    # SSE (Server-Sent Events) - Fallback for WebSocket
    path('api/sse/', include([
        path('ticket/', SSETicketView.as_view(), name='sse_ticket'),
        path('orders/', OrderSSEView.as_view(), name='sse_orders'),
        path('whatsapp/', WhatsAppSSEView.as_view(), name='sse_whatsapp'),
        path('health/', WebSocketHealthCheckView.as_view(), name='sse_health'),
    ])),

    # Unified Webhooks v1 (centralized handlers)
    # Meta WhatsApp API sends webhooks WITHOUT trailing slash for verification
    path('webhooks/v1/', include('apps.webhooks.urls')),
    path('webhooks/payments/mercadopago', MercadoPagoWebhookView.as_view(), name='mercadopago_webhook_no_slash'),
    path('webhooks/payments/mercadopago/', MercadoPagoWebhookView.as_view(), name='mercadopago_webhook'),
    # Slug-scoped: usado pelo link de pagamento (notification_url com slug) p/ o
    # webhook resolver a loja e reconciliar a cobrança por external_reference.
    path('webhooks/payments/mercadopago/<slug:store_slug>/', MercadoPagoWebhookView.as_view(), name='mercadopago_webhook_slug'),
    
    # Direct WhatsApp verification endpoint (no trailing slash required by Meta)
    # Regular webhook POSTs with trailing slash are already handled by webhooks/v1/ above.
    path('webhooks/v1/whatsapp', whatsapp_verification_view, name='whatsapp_webhook_no_slash'),

    # Instagram Business Login OAuth callback (registered redirect URI in Meta app)
    path('ig/callback', ig_oauth_callback, name='ig_oauth_callback'),
]

# Serve media files from local storage when explicitly enabled.
# In Docker production, nginx serves /media/ directly from the shared volume.
if getattr(settings, 'SERVE_MEDIA_FILES', False) and not getattr(settings, 'USE_S3', False):
    media_prefix = settings.MEDIA_URL.lstrip('/').rstrip('/')
    urlpatterns += [
        re_path(
            rf'^{media_prefix}/(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
