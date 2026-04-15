"""
Messaging API Views - LEGACY (Messenger específico).

DEPRECATED: Use messaging_v2 para a versão unificada (WhatsApp, Messenger, etc).
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import PlatformAccount, UnifiedConversation, UnifiedMessage
from .serializers import (
    PlatformAccountSerializer,
    UnifiedConversationSerializer,
    UnifiedMessageSerializer
)


class MessengerAccountViewSet(viewsets.ModelViewSet):
    """ViewSet LEGACY para contas - redireciona para PlatformAccount."""
    queryset = PlatformAccount.objects.filter(platform='messenger')
    serializer_class = PlatformAccountSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(created_by=self.request.user)


class MessengerConversationViewSet(viewsets.ModelViewSet):
    """ViewSet LEGACY para conversas - redireciona para UnifiedConversation."""
    queryset = UnifiedConversation.objects.filter(platform='messenger')
    serializer_class = UnifiedConversationSerializer
    permission_classes = [IsAuthenticated]


class MessengerMessageViewSet(viewsets.ModelViewSet):
    """ViewSet LEGACY para mensagens - redireciona para UnifiedMessage."""
    queryset = UnifiedMessage.objects.filter(conversation__platform='messenger')
    serializer_class = UnifiedMessageSerializer
    permission_classes = [IsAuthenticated]
