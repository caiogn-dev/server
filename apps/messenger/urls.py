"""
Messenger API URLs
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MessengerAccountViewSet,
    MessengerConversationViewSet,
    MessengerMessageViewSet,
    MessengerBroadcastViewSet,
    MessengerSponsoredViewSet
)

router = DefaultRouter()
router.register(r'accounts', MessengerAccountViewSet, basename='messenger-account')
router.register(r'conversations', MessengerConversationViewSet, basename='messenger-conversation')
router.register(r'messages', MessengerMessageViewSet, basename='messenger-message')
router.register(r'broadcasts', MessengerBroadcastViewSet, basename='messenger-broadcast')
router.register(r'sponsored', MessengerSponsoredViewSet, basename='messenger-sponsored')

urlpatterns = [
    path('', include(router.urls)),
]
