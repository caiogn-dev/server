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
    """Gerenciar contas de plataforma (WhatsApp, Instagram, Messenger)."""
    
    serializer_class = PlatformAccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['platform', 'is_active', 'is_verified', 'status']
    
    def get_queryset(self):
        """Retornar apenas contas do usuário logado."""
        return PlatformAccount.objects.filter(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def by_platform(self, request):
        """Listar contas agrupadas por plataforma."""
        platforms = {}
        for platform_code, platform_name in PlatformAccount.Platform.choices:
            accounts = self.get_queryset().filter(platform=platform_code)
            platforms[platform_code] = {
                'name': platform_name,
                'count': accounts.count(),
                'accounts': PlatformAccountSerializer(
                    accounts, many=True, context={'request': request}
                ).data
            }
        return Response(platforms)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Ativar conta."""
        account = self.get_object()
        account.is_active = True
        account.status = PlatformAccount.Status.ACTIVE
        account.save(update_fields=['is_active', 'status'])
        return Response({'status': 'activated'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Desativar conta."""
        account = self.get_object()
        account.is_active = False
        account.status = PlatformAccount.Status.INACTIVE
        account.save(update_fields=['is_active', 'status'])
        return Response({'status': 'deactivated'})
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """Sincronizar informações da conta com a plataforma."""
        account = self.get_object()
        # TODO: Implementar sincronização específica por plataforma
        return Response({
            'status': 'synced',
            'platform': account.platform,
            'account_id': str(account.id)
        })
    
    @action(detail=True, methods=['post'])
    def sync_templates(self, request, pk=None):
        """Sincronizar templates do WhatsApp."""
        account = self.get_object()
        if account.platform != 'whatsapp':
            return Response(
                {'error': 'Apenas contas WhatsApp suportam sincronização de templates'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task = sync_whatsapp_templates.delay(str(account.id))
        return Response({'task_id': task.id, 'status': 'syncing'})


class ConversationViewSet(viewsets.ModelViewSet):
    """Gerenciar conversas unificadas."""
    
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['platform', 'is_open', 'platform_account']
    
    def get_queryset(self):
        """Retornar conversas das contas do usuário."""
        queryset = Conversation.objects.filter(
            platform_account__user=self.request.user
        )
        
        # Filtro por busca
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(customer_name__icontains=search) |
                Q(customer_phone__icontains=search) |
                Q(customer_id__icontains=search)
            )
        
        return queryset.select_related('platform_account').annotate(
            message_count=Count('messages')
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
    def mark_read(self, request, pk=None):
        """Marcar conversa como lida."""
        conversation = self.get_object()
        conversation.unread_count = 0
        conversation.save(update_fields=['unread_count'])
        return Response({'status': 'marked_read'})
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Enviar mensagem na conversa."""
        conversation = self.get_object()
        text = request.data.get('text')
        message_type = request.data.get('message_type', 'text')
        
        if not text:
            return Response(
                {'error': 'Texto da mensagem é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Criar mensagem
        message = UnifiedMessage.objects.create(
            conversation=conversation,
            direction='outbound',
            message_type=message_type,
            text=text,
            status='pending'
        )
        
        # Enviar para a plataforma
        if conversation.platform == 'whatsapp':
            send_whatsapp_message.delay(str(message.id))
        
        return Response({
            'status': 'sent',
            'message_id': str(message.id)
        })


class UnifiedMessageViewSet(viewsets.ModelViewSet):
    """Gerenciar mensagens."""
    
    serializer_class = UnifiedMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['conversation', 'direction', 'status', 'message_type']
    
    def get_queryset(self):
        """Retornar mensagens das conversas do usuário."""
        return UnifiedMessage.objects.filter(
            conversation__platform_account__user=self.request.user
        ).select_related('conversation')


class MessageTemplateViewSet(viewsets.ModelViewSet):
    """Gerenciar templates de mensagem."""
    
    serializer_class = MessageTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['platform_account', 'status', 'category', 'language']
    
    def get_queryset(self):
        """Retornar templates das contas do usuário."""
        return MessageTemplate.objects.filter(
            platform_account__user=self.request.user
        ).select_related('platform_account')
