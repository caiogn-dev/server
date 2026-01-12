"""
URL configuration for unified API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UnifiedOrdersViewSet, UnifiedStatsView

router = DefaultRouter()
router.register(r'orders', UnifiedOrdersViewSet, basename='unified-orders')

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', UnifiedStatsView.as_view(), name='unified-stats'),
]
