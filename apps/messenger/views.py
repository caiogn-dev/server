"""
Backend - Messenger API Endpoints

Estes são os endpoints que o frontend espera encontrar.
Se não existirem no backend, copiar este arquivo.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
import logging

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class MessengerAccountViewSet(viewsets.ModelViewSet):
    """
    ViewSet para contas do Messenger (Facebook Pages).
    """
    queryset = MessengerAccount.objects.all()
    serializer_class = MessengerAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(store__members=self.request.user)
        return queryset
    
    @action(detail=True, methods=['post'])
    def verify_webhook(self, request, pk=None):
        """Verifica webhook do Facebook."""
        account = self.get_object()
        # Implementar verificação
        account.webhook_verified = True
        account.save()
        return Response({'status': 'verified', 'webhook_verified': True})


class MessengerConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para conversas do Messenger.
    """
    queryset = MessengerConversation.objects.all()
    serializer_class = MessengerConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtrar por conta
        account_id = self.request.query_params.get('account')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Filtrar por loja
        if not self.request.user.is_superuser:
            queryset = queryset.filter(account__store__members=self.request.user)
        
        return queryset.order_by('-updated_at')
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Retorna mensagens da conversa."""
        conversation = self.get_object()
        messages = MessengerMessage.objects.filter(conversation=conversation)
        
        # Paginação
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = MessengerMessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = MessengerMessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Envia mensagem na conversa."""
        conversation = self.get_object()
        content = request.data.get('content')
        message_type = request.data.get('message_type', 'text')
        
        # Enviar via Facebook Graph API
        # TODO: Implementar integração
        
        # Criar registro
        message = MessengerMessage.objects.create(
            conversation=conversation,
            sender_id=conversation.account.page_id,
            content=content,
            message_type=message_type,
            is_from_bot=True
        )
        
        # Atualizar conversa
        conversation.last_message = content
        conversation.save()
        
        serializer = MessengerMessageSerializer(message)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marca conversa como lida."""
        conversation = self.get_object()
        conversation.unread_count = 0
        conversation.save()
        
        MessengerMessage.objects.filter(
            conversation=conversation,
            is_read=False
        ).update(is_read=True)
        
        return Response({'status': 'marked as read'})


class MessengerBroadcastViewSet(viewsets.ModelViewSet):
    """
    ViewSet para broadcasts do Messenger.
    """
    queryset = MessengerBroadcast.objects.all()
    serializer_class = MessengerBroadcastSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(account__store__members=self.request.user)
        return queryset
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Agenda broadcast."""
        broadcast = self.get_object()
        scheduled_at = request.data.get('scheduled_at')
        broadcast.scheduled_at = scheduled_at
        broadcast.status = 'scheduled'
        broadcast.save()
        return Response({'status': 'scheduled'})
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancela broadcast."""
        broadcast = self.get_object()
        broadcast.status = 'cancelled'
        broadcast.save()
        return Response({'status': 'cancelled'})
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Envia broadcast imediatamente."""
        broadcast = self.get_object()
        # Implementar envio
        broadcast.status = 'sent'
        broadcast.save()
        return Response({'status': 'sent'})
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Retorna estatísticas do broadcast."""
        broadcast = self.get_object()
        return Response({
            'sent_count': broadcast.sent_count,
            'delivered_count': broadcast.delivered_count,
            'failed_count': broadcast.failed_count,
        })


class MessengerSponsoredViewSet(viewsets.ModelViewSet):
    """
    ViewSet para mensagens patrocinadas do Messenger.
    """
    queryset = MessengerSponsoredMessage.objects.all()
    serializer_class = MessengerSponsoredSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(account__store__members=self.request.user)
        return queryset
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publica mensagem patrocinada."""
        message = self.get_object()
        message.status = 'active'
        message.save()
        return Response({'status': 'published'})
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pausa mensagem patrocinada."""
        message = self.get_object()
        message.status = 'paused'
        message.save()
        return Response({'status': 'paused'})


# URLs para adicionar em urls.py:
"""
router = DefaultRouter()
router.register(r'messenger/accounts', MessengerAccountViewSet)
router.register(r'messenger/conversations', MessengerConversationViewSet)
router.register(r'messenger/broadcasts', MessengerBroadcastViewSet)
router.register(r'messenger/sponsored', MessengerSponsoredViewSet)

urlpatterns = [
    ...
    path('api/v1/', include(router.urls)),
]
"""
