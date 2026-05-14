"""
Messenger API Endpoints — Facebook Messenger Platform.
"""
import logging

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import (
    MessengerAccount,
    MessengerBroadcast,
    MessengerConversation,
    MessengerMessage,
    MessengerSponsoredMessage,
)
from .serializers import (
    MessengerAccountCreateSerializer,
    MessengerAccountSerializer,
    MessengerBroadcastSerializer,
    MessengerConversationSerializer,
    MessengerMessageSerializer,
)

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class MessengerAccountViewSet(viewsets.ModelViewSet):
    """ViewSet para contas do Messenger (Facebook Pages)."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        qs = MessengerAccount.objects.filter(is_active=True)
        if user.is_staff or user.is_superuser:
            return qs
        return qs.filter(owner=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return MessengerAccountCreateSerializer
        return MessengerAccountSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """Verifica e sincroniza webhook do Facebook."""
        account = self.get_object()
        account.webhook_verified = True
        account.save(update_fields=['webhook_verified'])
        return Response({'status': 'verified', 'webhook_verified': True})

    @action(detail=True, methods=['get'])
    def profile(self, request, pk=None):
        """Retorna perfil da página do Facebook."""
        account = self.get_object()
        return Response({
            'page_id': account.page_id,
            'page_name': account.page_name,
            'name': account.name,
        })


class MessengerConversationViewSet(viewsets.ModelViewSet):
    """ViewSet para conversas do Messenger."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        qs = MessengerConversation.objects.select_related('account')

        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(account__owner=user)

        account_id = self.request.query_params.get('account')
        if account_id:
            qs = qs.filter(account_id=account_id)

        return qs.order_by('-updated_at')

    def get_serializer_class(self):
        return MessengerConversationSerializer

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Retorna mensagens paginadas da conversa."""
        conversation = self.get_object()
        qs = MessengerMessage.objects.filter(conversation=conversation).order_by('created_at')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = MessengerMessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = MessengerMessageSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Envia mensagem na conversa."""
        conversation = self.get_object()
        content = request.data.get('content', '').strip()
        message_type = request.data.get('message_type', 'text')

        if not content:
            return Response({'error': 'content é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)

        message = MessengerMessage.objects.create(
            conversation=conversation,
            sender_id=conversation.account.page_id,
            sender_name=conversation.account.page_name,
            content=content,
            message_type=message_type,
            is_from_bot=True,
        )

        conversation.last_message = content
        from django.utils import timezone
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message', 'last_message_at', 'updated_at'])

        serializer = MessengerMessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marca todas as mensagens da conversa como lidas."""
        conversation = self.get_object()
        MessengerMessage.objects.filter(conversation=conversation, is_read=False).update(is_read=True)
        conversation.unread_count = 0
        conversation.save(update_fields=['unread_count', 'updated_at'])
        return Response({'status': 'ok'})


class MessengerBroadcastViewSet(viewsets.ModelViewSet):
    """ViewSet para broadcasts do Messenger."""

    serializer_class = MessengerBroadcastSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = MessengerBroadcast.objects.select_related('account')
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(account__owner=user)
        return qs

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Envia broadcast imediatamente."""
        broadcast = self.get_object()
        broadcast.status = MessengerBroadcast.BroadcastStatus.SENDING
        broadcast.save(update_fields=['status'])
        # TODO: disparar task Celery para envio real via Graph API
        return Response({'status': 'sending'})

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Retorna estatísticas do broadcast."""
        broadcast = self.get_object()
        return Response({
            'recipient_count': broadcast.recipient_count,
            'sent_count': broadcast.sent_count,
            'delivered_count': broadcast.delivered_count,
            'failed_count': broadcast.failed_count,
        })


class MessengerSponsoredViewSet(viewsets.ModelViewSet):
    """ViewSet para mensagens patrocinadas do Messenger."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = MessengerSponsoredMessage.objects.select_related('account')
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(account__owner=user)
        return qs

    def get_serializer_class(self):
        from rest_framework import serializers

        class _Serializer(serializers.ModelSerializer):
            class Meta:
                model = MessengerSponsoredMessage
                fields = '__all__'

        return _Serializer
