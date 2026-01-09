"""
E-commerce app URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import ProductViewSet, CartViewSet, CheckoutViewSet, WebhookViewSet, OrdersHistoryView

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'checkout', CheckoutViewSet, basename='checkout')
router.register(r'webhooks', WebhookViewSet, basename='ecommerce-webhook')

urlpatterns = [
    path('', include(router.urls)),
    path('orders/history/', OrdersHistoryView.as_view(), name='orders-history'),
]
