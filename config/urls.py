"""
URL configuration for Pastita E-commerce Platform.

Main API endpoints:
- /api/v1/stores/{store_slug}/ - Unified store API (catalog, cart, checkout, etc.; legacy /stores/s/{store_slug}/ paths remain available)
- /api/v1/auth/ - Authentication (login, register, logout)
- /api/v1/users/ - User profile management

Admin/Dashboard endpoints:
- /api/v1/stores/ - Store management (admin)
- /admin/ - Django admin

Webhooks:
- /webhooks/whatsapp/ - WhatsApp webhooks
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from apps.core.dashboard_views import DashboardStatsView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API v1
    path('api/v1/', include([
        # Core (auth, users, csrf)
        path('', include('apps.core.urls')),


        # Unified Store API (PRIMARY - used by frontends)
        path('stores/', include('apps.stores.urls')),

        # Dashboard/Admin APIs
        path('notifications/', include('apps.notifications.urls')),

        # WhatsApp, Instagram & Automation
        path('whatsapp/', include('apps.whatsapp.urls')),
        path('instagram/', include('apps.instagram.urls')),
        path('conversations/', include('apps.conversations.urls')),
        path('automation/', include('apps.automation.urls')),
        path('langflow/', include('apps.langflow.urls')),

        # Marketing & Audit
        path('marketing/', include('apps.marketing.urls')),
        path('campaigns/', include('apps.campaigns.urls')),  # WhatsApp campaigns
        path('audit/', include('apps.audit.urls')),
    ])),

    path('api/v1/core/dashboard-stats/', DashboardStatsView.as_view(), name='core-dashboard-stats'),

    # Webhooks (public endpoints)
    # IMPORTANT: Meta's WhatsApp API sends webhooks WITHOUT trailing slash
    # We need to handle both /webhooks/whatsapp and /webhooks/whatsapp/
    path('webhooks/', include([
        path('whatsapp/', include('apps.whatsapp.webhooks.urls')),
        path('payments/mercadopago/', include('apps.stores.webhooks_urls')),
        path('automation/', include('apps.automation.webhooks.urls')),
    ])),
    # Handle webhook without trailing slash (Meta sends POST to /webhooks/whatsapp)
    path('webhooks/whatsapp', include('apps.whatsapp.webhooks.urls')),
]

# Serve media files when not using S3 (e.g., local/dev or fallback)
if not getattr(settings, 'USE_S3', False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
