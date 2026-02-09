"""
URLs para Users app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UnifiedUserViewSet, UnifiedUserActivityViewSet

router = DefaultRouter()
router.register(r'users', UnifiedUserViewSet, basename='unified-user')
router.register(r'activities', UnifiedUserActivityViewSet, basename='user-activity')

urlpatterns = [
    path('', include(router.urls)),
]
