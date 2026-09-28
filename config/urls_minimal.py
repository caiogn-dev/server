"""URL configuration minimalista para testes de serializers."""
from django.urls import path, include

from apps.core.auth_views import ProfileView
from apps.stores.api.webhooks import MercadoPagoWebhookView

urlpatterns = [
    path('webhooks/v1/', include('apps.webhooks.urls')),
    path('webhooks/payments/mercadopago/', MercadoPagoWebhookView.as_view()),
    path('webhooks/payments/mercadopago/<slug:store_slug>/', MercadoPagoWebhookView.as_view()),
    path('api/v1/mobile/', include('apps.mobile_api.urls')),
    path('api/v1/auth/', include('apps.core.auth.urls')),
    path('api/v1/users/profile/', ProfileView.as_view()),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/stores/', include('apps.stores.urls')),
    path('api/v1/public/', include('apps.public_api.urls')),
    path('api/v1/marketing/', include('apps.marketing.urls')),
]
