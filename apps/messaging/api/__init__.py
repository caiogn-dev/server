"""Messaging API - LEGACY exports."""
from .views import (
    MessengerAccountViewSet,
    MessengerConversationViewSet,
    MessengerMessageViewSet,
)
from .serializers import (
    PlatformAccountSerializer as MessengerAccountSerializer,
    UnifiedConversationSerializer as MessengerConversationSerializer,
    UnifiedMessageSerializer as MessengerMessageSerializer,
)

__all__ = [
    'MessengerAccountViewSet',
    'MessengerConversationViewSet',
    'MessengerMessageViewSet',
    'MessengerAccountSerializer',
    'MessengerConversationSerializer',
    'MessengerMessageSerializer',
]
