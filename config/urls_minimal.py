"""URL configuration minimalista para testes de serializers."""
from django.urls import path, include

urlpatterns = [
    path('webhooks/v1/', include('apps.webhooks.urls')),
    path('api/v1/mobile/', include('apps.mobile_api.urls')),
    path('api/v1/auth/', include('apps.core.auth.urls')),
    path('api/v1/stores/', include('apps.stores.urls')),
]
