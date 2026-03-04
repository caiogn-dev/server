"""
Views completas para messaging_v2.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count

from .models import PlatformAccount, Conversation, UnifiedMessage, MessageTemplate
from .serializers import (
    PlatformAccountSerializer, ConversationSerializer,
    UnifiedMessageSerializer, MessageTemplateSerializer
)
from .tasks import send_whatsapp_message, sync_whatsapp_templates


class PlatformAccountViewSet(viewsets.ModelViewSet):
    """Gerenciar contas de plataforma (WhatsApp, Instagram, etc)."""
    queryset = PlatformAccount.objects.all()
    serializer_class = PlatformAccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['platform', 'is_active', 'is_verified']
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Ativar conta."""
        account = self.get_object()
        account.is_active = True
        account.save(update_fields=['is_active'])
        return Response({'status': 'activated'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Desativar conta."""
        account = self.get_object()
        account.is_active = False
        account.save(update_fields=['is_active'])
        return Response({'status': 'deactivated'})
    
    @action(detail=True, methods=['post'])
    def sync_templates(self, request, pk=None):
        """Sincronizar templates do WhatsApp."""
        account = self.get_object()
        if account.platform != 'whatsapp':
            return Response(
                {'error': 'Only WhatsApp accounts support template sync'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task = sync_whatsapp_templates.delay(str(account.id))
        return Response({'task_id': task.id, 'status': 'syncing'})


class ConversationViewSet(viewsets.ModelViewSet):
    """Gerenciar conversas."""
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['store', 'platform', 'is_open']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtro por busca
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(customer_name__icontains=search) |
                Q(customer_phone__icontains=search)
            )
        
        return queryset.select_related('store').annotate(
            unread_count=Count('messages', filter=Q(messages__status='delivered'))
        )
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Fechar conversa."""
        conversation = self.get_object()
        conversation.is_open = False
        conversation.save(update_fields=['is_open'])
        return Response({'status': 'closed'})
    
    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reabrir conversa."""
        conversation = self.get_object()
        conversation.is_open = True
        conversation.save(update_fields=['is_open'])
        return Response({'status': 'reopened'})
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Enviar mensagem na conversa."""
        conversation = self.get_object()
        text = request.data.get('text')
        
        if not text:
            return Response(
                {'error': 'Text is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Criar mensagem
        message = UnifiedMessage.objects.create(
            conversation=conversation,
            direction=UnifiedMessage.Direction.OUTBOUND,
            text=text
        )
        
        # Enviar via Celery
        task = send_whatsapp_message.delay(str(message.id))
        
        return Response({
            'message_id': str(message.id),
            'task_id': task.id,
            'status': 'sending'
        })


class UnifiedMessageViewSet(viewsets.ModelViewSet):
    """Gerenciar mensagens."""
    queryset = UnifiedMessage.objects.all()
    serializer_class = UnifiedMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['conversation', 'direction', 'status']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        conversation_id = self.request.query_params.get('conversation')
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        return queryset.select_related('conversation')


class MessageTemplateViewSet(viewsets.ModelViewSet):
    """Gerenciar templates de mensagem."""
    queryset = MessageTemplate.objects.all()
    serializer_class = MessageTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'category', 'language']
