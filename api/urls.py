from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views

router = DefaultRouter()

# User management
router.register(r'users', views.UserViewSet, basename='user')

# Product catalog
router.register(r'products', views.ProductViewSet, basename='product')

# Shopping cart
router.register(r'cart', views.CartViewSet, basename='cart')

# Orders
router.register(r'orders', views.OrderViewSet, basename='order')

# Checkout and payment
router.register(r'checkout', views.CheckoutViewSet, basename='checkout')

# Webhooks for external services
router.register(r'webhooks', views.WebhookViewSet, basename='webhook')

urlpatterns = [
    path('', include(router.urls)),
    path('login/', obtain_auth_token, name='api_token_auth'),
    path('health/', views.HealthCheckView.as_view(), name='health_check'),
    path('csrf/', views.get_csrf_token, name='csrf_token'),  # CSRF token endpoint
]