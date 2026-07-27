"""URL configuration minimalista para testes de serializers."""
from django.urls import path, include

urlpatterns = [
    path('webhooks/v1/', include('apps.webhooks.urls')),
]
