"""
Payment API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import PaymentViewSet, PaymentGatewayViewSet

router = DefaultRouter()
router.register(r'', PaymentViewSet, basename='payment')
router.register(r'gateways', PaymentGatewayViewSet, basename='payment-gateway')

urlpatterns = [
    path('', include(router.urls)),
]
