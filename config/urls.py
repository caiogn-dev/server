"""
URL configuration for Pastita E-commerce Platform.

Main API endpoints:
- /api/v1/stores/s/{store_slug}/ - Unified store API (catalog, cart, checkout, etc.)
- /api/v1/auth/ - Authentication (login, register, logout)
- /api/v1/users/ - User profile management

Admin/Dashboard endpoints:
- /api/v1/unified/ - Unified dashboard APIs
- /api/v1/stores/ - Store management (admin)
- /admin/ - Django admin

Webhooks:
- /webhooks/payments/ - Payment provider webhooks
- /webhooks/whatsapp/ - WhatsApp webhooks
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

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
        path('unified/', include('apps.unified.api.urls')),
        path('orders/', include('apps.orders.urls')),
        path('payments/', include('apps.payments.urls')),
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

    # Webhooks (public endpoints)
    path('webhooks/', include([
        path('whatsapp/', include('apps.whatsapp.webhooks.urls')),
        path('payments/', include('apps.payments.webhooks.urls')),
        path('payments/mercadopago/', include('apps.stores.webhooks_urls')),
        path('automation/', include('apps.automation.webhooks.urls')),
    ])),
]
