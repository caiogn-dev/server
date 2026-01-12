"""
Payment API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import PaymentViewSet, PaymentGatewayViewSet

# Use separate routers to avoid conflicts with empty prefix
payment_router = DefaultRouter()
payment_router.register(r'', PaymentViewSet, basename='payment')

gateway_router = DefaultRouter()
gateway_router.register(r'', PaymentGatewayViewSet, basename='payment-gateway')

urlpatterns = [
    # Gateways first to avoid being caught by empty prefix
    path('gateways/', include(gateway_router.urls)),
    path('', include(payment_router.urls)),
]
