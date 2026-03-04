"""URL configuration - NOVA (apenas apps v2)."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core_v2.views import LoginView, LogoutView, HealthCheckView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', HealthCheckView.as_view(), name='health_check'),
    path('api/v1/auth/login/', LoginView.as_view(), name='api_login'),
    path('api/v1/auth/logout/', LogoutView.as_view(), name='api_logout'),
    path('api/v1/commerce/', include('apps.commerce.urls')),
    path('api/v1/messaging/', include('apps.messaging_v2.urls')),
    path('api/v1/marketing/', include('apps.marketing_v2.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
