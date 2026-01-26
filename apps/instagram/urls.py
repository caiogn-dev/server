"""
Instagram app URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    InstagramAccountViewSet,
    InstagramConversationViewSet,
    InstagramMessageViewSet,
    InstagramWebhookView,
    InstagramWebhookEventViewSet
)

router = DefaultRouter()
router.register(r'accounts', InstagramAccountViewSet, basename='instagram-account')
router.register(r'conversations', InstagramConversationViewSet, basename='instagram-conversation')
router.register(r'messages', InstagramMessageViewSet, basename='instagram-message')
router.register(r'webhook-events', InstagramWebhookEventViewSet, basename='instagram-webhook-event')

urlpatterns = [
    path('', include(router.urls)),
    path('webhook/', InstagramWebhookView.as_view(), name='instagram-webhook'),
]
