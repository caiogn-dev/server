"""
Core v2 - URL configuration.

Routes for User management and authentication.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from rest_framework_simplejwt.views import TokenRefreshView

from .views import UserViewSet, LoginView, LogoutView

# Create router and register viewsets
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

# URL patterns
urlpatterns = [
    # Router URLs (includes users CRUD)
    path('', include(router.urls)),
    
    # Authentication endpoints
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
