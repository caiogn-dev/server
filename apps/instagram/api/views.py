from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta

from ..models import (
    InstagramAccount, InstagramMedia, InstagramConversation, 
    InstagramMessage, InstagramLive, InstagramCatalog, 
    InstagramProduct, InstagramScheduledPost, InstagramInsight
)
from ..services import (
    InstagramAPI, InstagramGraphService, InstagramShoppingService,
    InstagramLiveService, InstagramDirectService
)


class InstagramAccountViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de contas Instagram"""
    queryset = InstagramAccount.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """Sincroniza informações da conta com o Instagram"""
        account = self.get_object()
        api = InstagramAPI(account)
        
        if api.sync_account_info():
            return Response({'status': 'success', 'message': 'Conta sincronizada'})
        return Response(
            {'status': 'error', 'message': 'Falha na sincronização'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['get'])
    def insights(self, request, pk=None):
        """Obtém insights da conta"""
        account = self.get_object()
        days = int(request.query_params.get('days', 30))
        
        since = timezone.now() - timedelta(days=days)
        until = timezone.now()
        
        api = InstagramAPI(account)
        graph_service = InstagramGraphService(api)
        
        try:
            insights = graph_service.get_account_insights(since, until)
            return Response(insights)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class InstagramMediaViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de mídias (Posts, Stories, Reels)"""
    queryset = InstagramMedia.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(account__user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def feed(self, request):
        """Lista feed de posts"""
        queryset = self.get_queryset().filter(
            media_type__in=['IMAGE', 'VIDEO', 'CAROUSEL_ALBUM']
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stories(self, request):
        """Lista stories"""
        queryset = self.get_queryset().filter(media_type='STORY')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def reels(self, request):
        """Lista reels"""
        queryset = self.get_queryset().filter(media_type='REELS')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publica uma mídia"""
        media = self.get_object()
        api = InstagramAPI(media.account)
        graph_service = InstagramGraphService(api)
        
        try:
            result = graph_service.publish_media(
                media.media_type,
                media.media_url,
                media.caption
            )
            media.instagram_media_id = result.get('id')
            media.status = 'PUBLISHED'
            media.published_at = timezone.now()
            media.save()
            return Response({'status': 'success', 'id': result.get('id')})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Agenda uma publicação"""
        media = self.get_object()
        schedule_time = request.data.get('schedule_time')
        
        if not schedule_time:
            return Response(
                {'error': 'schedule_time é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        media.status = 'SCHEDULED'
        media.scheduled_at = schedule_time
        media.save()
        
        return Response({'status': 'scheduled'})
    
    @action(detail=True, methods=['get'])
    def insights(self, request, pk=None):
        """Obtém insights da mídia"""
        media = self.get_object()
        api = InstagramAPI(media.account)
        graph_service = InstagramGraphService(api)
        
        try:
            insights = graph_service.get_media_insights(media.instagram_media_id)
            return Response(insights)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def comments(self, request, pk=None):
        """Obtém comentários da mídia"""
        media = self.get_object()
        api = InstagramAPI(media.account)
        graph_service = InstagramGraphService(api)
        
        try:
            comments = graph_service.get_comments(media.instagram_media_id)
            return Response(comments)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class InstagramShoppingViewSet(viewsets.ViewSet):
    """ViewSet para gerenciamento de Shopping"""
    permission_classes = [IsAuthenticated]
    
    def get_account(self):
        account_id = self.request.query_params.get('account_id')
        return get_object_or_404(InstagramAccount, id=account_id, user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def catalogs(self, request):
        """Lista catálogos"""
        account = self.get_account()
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        return Response(service.list_catalogs())
    
    @action(detail=False, methods=['get'])
    def products(self, request):
        """Lista produtos"""
        account = self.get_account()
        catalog_id = request.query_params.get('catalog_id')
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        return Response(service.list_products(catalog_id))
    
    @action(detail=False, methods=['post'])
    def tag_product(self, request):
        """Adiciona tag de produto a uma mídia"""
        account = self.get_account()
        media_id = request.data.get('media_id')
        product_id = request.data.get('product_id')
        x = request.data.get('x', 0.5)
        y = request.data.get('y', 0.5)
        
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        
        try:
            tag = service.add_tag_to_media(media_id, product_id, x, y)
            return Response({'status': 'success', 'tag_id': str(tag.id)})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def settings(self, request):
        """Obtém configurações de shopping"""
        account = self.get_account()
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        return Response(service.get_shopping_settings())


class InstagramLiveViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de Lives"""
    queryset = InstagramLive.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(account__user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Inicia uma live"""
        live = self.get_object()
        api = InstagramAPI(live.account)
        service = InstagramLiveService(api)
        
        try:
            result = service.start_live(str(live.id))
            return Response(result)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        """Finaliza uma live"""
        live = self.get_object()
        api = InstagramAPI(live.account)
        service = InstagramLiveService(api)
        
        if service.end_live(str(live.id)):
            return Response({'status': 'ended'})
        return Response(
            {'error': 'Falha ao finalizar'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['get'])
    def comments(self, request, pk=None):
        """Obtém comentários da live"""
        live = self.get_object()
        api = InstagramAPI(live.account)
        service = InstagramLiveService(api)
        return Response(service.get_comments(str(live.id)))


class InstagramConversationViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de conversas do Direct"""
    queryset = InstagramConversation.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(account__user=self.request.user, is_active=True)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Obtém mensagens da conversa"""
        conversation = self.get_object()
        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)
        
        messages = service.get_messages(str(conversation.id))
        return Response(messages)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Envia mensagem na conversa"""
        conversation = self.get_object()
        message_type = request.data.get('type', 'TEXT')
        content = request.data.get('content', '')
        media_url = request.data.get('media_url')
        reply_to_id = request.data.get('reply_to')
        
        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)
        
        try:
            message = service.send_message(
                str(conversation.id),
                message_type,
                content=content,
                media_url=media_url,
                reply_to_id=reply_to_id
            )
            return Response({
                'id': str(message.id),
                'status': 'sent',
                'created_at': message.created_at.isoformat()
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marca conversa como lida"""
        conversation = self.get_object()
        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)
        
        if service.mark_as_read(str(conversation.id)):
            return Response({'status': 'marked_as_read'})
        return Response(
            {'error': 'Falha ao marcar'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Arquiva conversa"""
        conversation = self.get_object()
        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)
        
        if service.archive_conversation(str(conversation.id)):
            return Response({'status': 'archived'})
        return Response(
            {'error': 'Falha ao arquivar'},
            status=status.HTTP_400_BAD_REQUEST
        )


class InstagramMessageViewSet(viewsets.ViewSet):
    """ViewSet para operações em mensagens individuais"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def react(self, request):
        """Adiciona reação a mensagem"""
        message_id = request.data.get('message_id')
        reaction = request.data.get('reaction')
        
        # Implementar lógica de reação
        return Response({'status': 'success'})
    
    @action(detail=False, methods=['post'])
    def unsend(self, request):
        """Remove mensagem (unsend)"""
        message_id = request.data.get('message_id')
        # Implementar lógica de unsend
        return Response({'status': 'success'})


class InstagramWebhookViewSet(viewsets.ViewSet):
    """ViewSet para processamento de webhooks"""
    permission_classes = []  # Webhooks não requerem autenticação
    
    def create(self, request):
        """Processa webhook do Instagram"""
        # Verificar assinatura
        # Processar payload
        # Criar logs
        return Response({'status': 'received'})
    
    @action(detail=False, methods=['get'])
    def verify(self, request):
        """Verificação do webhook pelo Facebook"""
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        if mode == 'subscribe' and token == settings.INSTAGRAM_VERIFY_TOKEN:
            return Response(int(challenge))
        return Response('Verification failed', status=403)