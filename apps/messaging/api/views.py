from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.conf import settings

from ..models import (
    MessengerAccount, MessengerProfile, MessengerConversation,
    MessengerMessage, MessengerBroadcast, MessengerSponsoredMessage,
    MessengerExtension, MessengerWebhookLog
)
from ..services import MessengerService, MessengerPlatformService, MessengerBroadcastService


class MessengerAccountViewSet(viewsets.ModelViewSet):
    """ViewSet para contas do Messenger"""
    queryset = MessengerAccount.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """Sincroniza informações da página"""
        account = self.get_object()
        messenger = MessengerService(account)
        
        try:
            # Obtém informações da página
            page_info = messenger.get(account.page_id)
            account.page_name = page_info.get('name', account.page_name)
            account.category = page_info.get('category', '')
            account.followers_count = page_info.get('followers_count', 0)
            account.last_sync_at = __import__('django.utils.timezone').utils.timezone.now()
            account.save()
            
            return Response({'status': 'success'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class MessengerProfileViewSet(viewsets.ViewSet):
    """ViewSet para configurações de perfil do Messenger"""
    permission_classes = [IsAuthenticated]
    
    def get_account(self):
        account_id = self.request.query_params.get('account_id')
        return get_object_or_404(MessengerAccount, id=account_id, user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def get(self, request):
        """Obtém configurações de perfil"""
        account = self.get_account()
        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)
        
        profile = platform.get_profile()
        return Response(profile)
    
    @action(detail=False, methods=['post'])
    def greeting(self, request):
        """Define mensagem de saudação"""
        account = self.get_account()
        text = request.data.get('text')
        locale = request.data.get('locale', 'default')
        
        if not text:
            return Response(
                {'error': 'text é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)
        
        if platform.set_greeting(text, locale):
            return Response({'status': 'success'})
        return Response(
            {'error': 'Falha ao definir saudação'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def get_started(self, request):
        """Define botão de início"""
        account = self.get_account()
        payload = request.data.get('payload', 'GET_STARTED')
        
        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)
        
        if platform.set_get_started_button(payload):
            return Response({'status': 'success'})
        return Response(
            {'error': 'Falha ao definir botão'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def persistent_menu(self, request):
        """Define menu persistente"""
        account = self.get_account()
        menu_items = request.data.get('menu_items', [])
        
        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)
        
        if platform.set_persistent_menu(menu_items):
            return Response({'status': 'success'})
        return Response(
            {'error': 'Falha ao definir menu'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def ice_breakers(self, request):
        """Define quebras de gelo"""
        account = self.get_account()
        ice_breakers = request.data.get('ice_breakers', [])
        
        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)
        
        if platform.set_ice_breakers(ice_breakers):
            return Response({'status': 'success'})
        return Response(
            {'error': 'Falha ao definir ice breakers'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def whitelist_domains(self, request):
        """Define domínios permitidos"""
        account = self.get_account()
        domains = request.data.get('domains', [])
        
        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)
        
        if platform.whitelist_domains(domains):
            return Response({'status': 'success'})
        return Response(
            {'error': 'Falha ao definir domínios'},
            status=status.HTTP_400_BAD_REQUEST
        )


class MessengerConversationViewSet(viewsets.ModelViewSet):
    """ViewSet para conversas do Messenger"""
    queryset = MessengerConversation.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(account__user=self.request.user, is_active=True)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Obtém mensagens da conversa"""
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)
        platform = MessengerPlatformService(messenger)
        
        messages = platform.get_messages(str(conversation.id))
        return Response(messages)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Envia mensagem na conversa"""
        conversation = self.get_object()
        message_type = request.data.get('type', 'text')
        content = request.data.get('content', '')
        attachment_url = request.data.get('attachment_url')
        
        messenger = MessengerService(conversation.account)
        
        try:
            if message_type == 'text':
                result = messenger.send_text_message(conversation.psid, content)
            elif message_type == 'image':
                result = messenger.send_image(conversation.psid, attachment_url)
            elif message_type == 'video':
                result = messenger.send_video(conversation.psid, attachment_url)
            elif message_type == 'audio':
                result = messenger.send_audio(conversation.psid, attachment_url)
            elif message_type == 'template':
                template = request.data.get('template', {})
                result = messenger.send_template(conversation.psid, template)
            else:
                return Response(
                    {'error': 'Tipo de mensagem inválido'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Registra mensagem no banco
            MessengerMessage.objects.create(
                conversation=conversation,
                message_type=message_type.upper(),
                content=content,
                attachment_url=attachment_url,
                is_from_page=True,
                messenger_message_id=result.get('message_id')
            )
            
            return Response({'status': 'sent', 'id': result.get('message_id')})
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marca conversa como lida"""
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)
        platform = MessengerPlatformService(messenger)
        
        # Marca na API
        messenger.mark_seen(conversation.psid)
        
        # Marca localmente
        if platform.mark_conversation_read(str(conversation.id)):
            return Response({'status': 'marked_as_read'})
        return Response(
            {'error': 'Falha ao marcar'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def typing_on(self, request, pk=None):
        """Indica que está digitando"""
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)
        
        result = messenger.typing_on(conversation.psid)
        return Response({'status': 'typing_on'})
    
    @action(detail=True, methods=['post'])
    def typing_off(self, request, pk=None):
        """Remove indicador de digitação"""
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)
        
        result = messenger.typing_off(conversation.psid)
        return Response({'status': 'typing_off'})


class MessengerBroadcastViewSet(viewsets.ModelViewSet):
    """ViewSet para broadcasts"""
    queryset = MessengerBroadcast.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(account__user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Envia broadcast"""
        broadcast = self.get_object()
        messenger = MessengerService(broadcast.account)
        broadcast_service = MessengerBroadcastService(messenger)
        
        if broadcast_service.send_broadcast(str(broadcast.id)):
            return Response({'status': 'sending'})
        return Response(
            {'error': 'Falha ao enviar broadcast'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['get'])
    def insights(self, request, pk=None):
        """Obtém métricas do broadcast"""
        broadcast = self.get_object()
        messenger = MessengerService(broadcast.account)
        broadcast_service = MessengerBroadcastService(messenger)
        
        insights = broadcast_service.get_broadcast_insights(str(broadcast.id))
        return Response(insights)
    
    @action(detail=False, methods=['get'])
    def tags(self, request):
        """Lista tags de mensagem disponíveis"""
        account_id = request.query_params.get('account_id')
        account = get_object_or_404(MessengerAccount, id=account_id, user=request.user)
        
        messenger = MessengerService(account)
        broadcast_service = MessengerBroadcastService(messenger)
        
        tags = broadcast_service.get_message_tags()
        return Response(tags)


class MessengerSponsoredViewSet(viewsets.ModelViewSet):
    """ViewSet para mensagens patrocinadas"""
    queryset = MessengerSponsoredMessage.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(account__user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submete para aprovação"""
        sponsored = self.get_object()
        messenger = MessengerService(sponsored.account)
        broadcast_service = MessengerBroadcastService(messenger)
        
        if broadcast_service.submit_sponsored_message(str(sponsored.id)):
            return Response({'status': 'submitted'})
        return Response(
            {'error': 'Falha ao submeter'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pausa mensagem patrocinada"""
        sponsored = self.get_object()
        messenger = MessengerService(sponsored.account)
        broadcast_service = MessengerBroadcastService(messenger)
        
        if broadcast_service.pause_sponsored_message(str(sponsored.id)):
            return Response({'status': 'paused'})
        return Response(
            {'error': 'Falha ao pausar'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Retoma mensagem patrocinada"""
        sponsored = self.get_object()
        messenger = MessengerService(sponsored.account)
        broadcast_service = MessengerBroadcastService(messenger)
        
        if broadcast_service.resume_sponsored_message(str(sponsored.id)):
            return Response({'status': 'resumed'})
        return Response(
            {'error': 'Falha ao retomar'},
            status=status.HTTP_400_BAD_REQUEST
        )


class MessengerWebhookViewSet(viewsets.ViewSet):
    """ViewSet para webhooks do Messenger"""
    permission_classes = []
    
    def create(self, request):
        """Processa webhook do Messenger"""
        from ..tasks import process_messenger_webhook
        
        payload = request.data
        process_messenger_webhook.delay(payload)
        
        return Response({'status': 'received'})
    
    @action(detail=False, methods=['get'])
    def verify(self, request):
        """Verificação do webhook"""
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        if mode == 'subscribe' and token == getattr(settings, 'MESSENGER_VERIFY_TOKEN', ''):
            return Response(int(challenge))
        return Response('Verification failed', status=403)