"""
Notification API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import NotificationViewSet, NotificationPreferenceViewSet, PushSubscriptionViewSet
from .api.views import vapid_public_key

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')
router.register(r'preferences', NotificationPreferenceViewSet, basename='notification-preference')
router.register(r'push', PushSubscriptionViewSet, basename='push-subscription')

urlpatterns = [
    path('push/vapid-public-key/', vapid_public_key, name='vapid-public-key'),
    path('', include(router.urls)),
]
