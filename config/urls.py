"""
URL configuration for WhatsApp Business Platform.
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
        path('', include('apps.core.urls')),
        path('', include('apps.ecommerce.legacy_urls')),
        path('whatsapp/', include('apps.whatsapp.urls')),
        path('conversations/', include('apps.conversations.urls')),
        path('orders/', include('apps.orders.urls')),
        path('payments/', include('apps.payments.urls')),
        path('langflow/', include('apps.langflow.urls')),
        path('notifications/', include('apps.notifications.urls')),
        path('audit/', include('apps.audit.urls')),
        path('marketing/', include('apps.campaigns.urls')),
        path('automation/', include('apps.automation.urls')),
        path('ecommerce/', include('apps.ecommerce.urls')),
        path('stores/', include('apps.stores.urls')),  # Multi-store management API (unified)
        path('unified/', include('apps.unified.api.urls')),  # Unified APIs for dashboard
    ])),
    
    # Webhooks (public endpoints)
    path('webhooks/', include([
        path('whatsapp/', include('apps.whatsapp.webhooks.urls')),
        path('payments/', include('apps.payments.webhooks.urls')),
        path('automation/', include('apps.automation.webhooks.urls')),
    ])),
]
