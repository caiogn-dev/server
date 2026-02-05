"""
Instagram API Views.
"""
import logging
import requests
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from django.conf import settings
from urllib.parse import urlencode

from apps.instagram.models import (
    InstagramAccount,
    InstagramConversation,
    InstagramMessage,
    InstagramWebhookEvent
)
from apps.instagram.services import InstagramAPIService, InstagramMessageService
from apps.instagram.services.instagram_api import InstagramAPIError
from apps.instagram.webhooks import InstagramWebhookHandler
from .serializers import (
    InstagramAccountSerializer,
    InstagramAccountCreateSerializer,
    InstagramConversationSerializer,
    InstagramMessageSerializer,
    SendMessageSerializer,
    InstagramWebhookEventSerializer
)

logger = logging.getLogger(__name__)


class InstagramAccountViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Instagram accounts."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return InstagramAccount.objects.filter(owner=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InstagramAccountCreateSerializer
        return InstagramAccountSerializer
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
    
    @action(detail=True, methods=['get'])
    def sync_profile(self, request, pk=None):
        """Sync account profile from Instagram API."""
        account = self.get_object()
        
        try:
            api = InstagramAPIService(account)
            profile = api.get_account_info()
            
            account.username = profile.get('username', account.username)
            account.profile_picture_url = profile.get('profile_picture_url', '')
            account.followers_count = profile.get('followers_count', 0)
            account.save(update_fields=[
                'username', 
                'profile_picture_url', 
                'followers_count',
                'updated_at'
            ])
            
            return Response(InstagramAccountSerializer(account).data)
            
        except InstagramAPIError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def refresh_token(self, request, pk=None):
        """Refresh the access token."""
        account = self.get_object()
        
        try:
            api = InstagramAPIService(account)
            result = api.refresh_long_lived_token()
            
            account.access_token = result.get('access_token')
            if 'expires_in' in result:
                from django.utils import timezone
                from datetime import timedelta
                account.token_expires_at = timezone.now() + timedelta(seconds=result['expires_in'])
            
            account.status = InstagramAccount.AccountStatus.ACTIVE
            account.save()
            
            return Response({
                'success': True,
                'message': 'Token refreshed successfully',
                'expires_at': account.token_expires_at
            })
            
        except InstagramAPIError as e:
            account.status = InstagramAccount.AccountStatus.EXPIRED
            account.save(update_fields=['status', 'updated_at'])
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def set_ice_breakers(self, request, pk=None):
        """Set ice breakers for the account.
        
        Ice breakers allow users to start conversations with predefined questions.
        Example: [{'question': 'Ver cardápio', 'payload': 'GET_MENU'}, ...]
        """
        account = self.get_object()
        ice_breakers = request.data.get('ice_breakers', [])
        
        if not isinstance(ice_breakers, list):
            return Response(
                {'error': 'ice_breakers must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate format
        for ib in ice_breakers:
            if not isinstance(ib, dict) or 'question' not in ib or 'payload' not in ib:
                return Response(
                    {'error': 'Each ice breaker must have "question" and "payload"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        try:
            api = InstagramAPIService(account)
            result = api.set_ice_breakers(ice_breakers)
            
            # Store in account metadata for reference
            account.metadata = account.metadata or {}
            account.metadata['ice_breakers'] = ice_breakers
            account.save(update_fields=['metadata', 'updated_at'])
            
            logger.info(f"Ice breakers configured for account {account.id}", extra={
                'account_id': account.id,
                'ice_breakers_count': len(ice_breakers)
            })
            
            return Response({
                'success': True,
                'result': result,
                'ice_breakers': ice_breakers
            })
        except InstagramAPIError as e:
            logger.error(f"Failed to set ice breakers: {e}", extra={
                'account_id': account.id,
                'error_code': getattr(e, 'code', None)
            })
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get account statistics."""
        account = self.get_object()
        
        total_conversations = account.conversations.count()
        active_conversations = account.conversations.filter(
            status=InstagramConversation.ConversationStatus.ACTIVE
        ).count()
        total_messages = account.messages.count()
        inbound_messages = account.messages.filter(
            direction=InstagramMessage.MessageDirection.INBOUND
        ).count()
        outbound_messages = account.messages.filter(
            direction=InstagramMessage.MessageDirection.OUTBOUND
        ).count()
        
        return Response({
            'total_conversations': total_conversations,
            'active_conversations': active_conversations,
            'total_messages': total_messages,
            'inbound_messages': inbound_messages,
            'outbound_messages': outbound_messages
        })
    
    @action(detail=True, methods=['post'])
    def sync_conversations(self, request, pk=None):
        """Sync conversations from Instagram API."""
        account = self.get_object()
        
        try:
            api = InstagramAPIService(account)
            data = api.get_conversations(limit=50)
            
            conversations_data = data.get('data', [])
            synced = 0
            errors = 0
            
            for conv_data in conversations_data:
                try:
                    # Get participant info
                    participants = conv_data.get('participants', {}).get('data', [])
                    participant = None
                    for p in participants:
                        if p.get('id') != account.instagram_account_id:
                            participant = p
                            break
                    
                    if not participant:
                        continue
                    
                    participant_id = participant.get('id', '')
                    
                    # Create or update conversation
                    conversation, created = InstagramConversation.objects.update_or_create(
                        account=account,
                        participant_id=participant_id,
                        defaults={
                            'participant_username': participant.get('username', ''),
                            'participant_name': participant.get('name', participant.get('username', '')),
                            'participant_profile_pic': participant.get('profile_pic', ''),
                            'status': InstagramConversation.ConversationStatus.ACTIVE,
                        }
                    )
                    
                    # Sync messages from this conversation
                    messages_data = conv_data.get('messages', {}).get('data', [])
                    for msg_data in messages_data:
                        msg_from = msg_data.get('from', {})
                        msg_to = msg_data.get('to', {}).get('data', [{}])[0] if msg_data.get('to') else {}
                        
                        is_outbound = msg_from.get('id') == account.instagram_account_id
                        
                        InstagramMessage.objects.update_or_create(
                            account=account,
                            instagram_message_id=msg_data.get('id', ''),
                            defaults={
                                'conversation': conversation,
                                'direction': 'outbound' if is_outbound else 'inbound',
                                'message_type': 'text',
                                'status': 'delivered',
                                'sender_id': msg_from.get('id', ''),
                                'recipient_id': msg_to.get('id', '') if msg_to else participant_id,
                                'text_content': msg_data.get('message', ''),
                                'sent_at': msg_data.get('created_time'),
                            }
                        )
                    
                    # Update conversation stats
                    conversation.message_count = conversation.messages.count()
                    last_msg = conversation.messages.order_by('-created_at').first()
                    if last_msg:
                        conversation.last_message_at = last_msg.created_at
                        conversation.last_message_preview = last_msg.text_content[:100] if last_msg.text_content else ''
                    conversation.save()
                    
                    synced += 1
                    
                except Exception as e:
                    logger.error(f"Error syncing conversation: {e}")
                    errors += 1
            
            return Response({
                'success': True,
                'synced': synced,
                'errors': errors,
                'total_found': len(conversations_data)
            })
            
        except InstagramAPIError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class InstagramConversationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Instagram conversations."""
    
    serializer_class = InstagramConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        account_id = self.request.query_params.get('account_id')
        queryset = InstagramConversation.objects.filter(
            account__owner=self.request.user
        )
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.select_related('account', 'assigned_to')
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close a conversation."""
        conversation = self.get_object()
        conversation.status = InstagramConversation.ConversationStatus.CLOSED
        conversation.save(update_fields=['status', 'updated_at'])
        return Response(InstagramConversationSerializer(conversation).data)
    
    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen a conversation."""
        conversation = self.get_object()
        conversation.status = InstagramConversation.ConversationStatus.ACTIVE
        conversation.save(update_fields=['status', 'updated_at'])
        return Response(InstagramConversationSerializer(conversation).data)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign conversation to a user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        conversation = self.get_object()
        user_id = request.data.get('user_id')
        
        if user_id:
            user = get_object_or_404(User, id=user_id)
            conversation.assigned_to = user
        else:
            conversation.assigned_to = None
        
        conversation.save(update_fields=['assigned_to', 'updated_at'])
        return Response(InstagramConversationSerializer(conversation).data)


class InstagramMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Instagram messages."""
    
    serializer_class = InstagramMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post']
    
    def get_queryset(self):
        conversation_id = self.request.query_params.get('conversation_id')
        account_id = self.request.query_params.get('account_id')
        
        queryset = InstagramMessage.objects.filter(
            account__owner=self.request.user
        )
        
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        return queryset.select_related('account', 'conversation').order_by('created_at')
    
    def create(self, request, *args, **kwargs):
        """Send a new message."""
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        account_id = request.data.get('account_id')
        conversation_id = request.data.get('conversation_id')
        
        if not account_id:
            return Response(
                {'error': 'account_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        account = get_object_or_404(
            InstagramAccount, 
            id=account_id, 
            owner=request.user
        )
        
        # Se conversation_id foi fornecido, buscar o recipient_id da conversa
        recipient_id = serializer.validated_data.get('recipient_id')
        if conversation_id and not recipient_id:
            conversation = get_object_or_404(
                InstagramConversation,
                id=conversation_id,
                account=account
            )
            recipient_id = conversation.participant_id
            logger.info(f"Resolved recipient_id from conversation", extra={
                'conversation_id': conversation_id,
                'recipient_id': recipient_id
            })
        
        if not recipient_id:
            return Response(
                {'error': 'Either recipient_id or conversation_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = InstagramMessageService(account)
        
        try:
            data = serializer.validated_data
            
            logger.info(f"Sending Instagram message to {recipient_id}", extra={
                'account_id': account_id,
                'conversation_id': conversation_id,
                'recipient_id': recipient_id,
                'has_text': bool(data.get('text')),
                'has_image': bool(data.get('image_url'))
            })
            
            if data.get('text'):
                if data.get('quick_replies'):
                    message = service.send_quick_replies(
                        recipient_id,
                        data['text'],
                        data['quick_replies']
                    )
                else:
                    message = service.send_text(recipient_id, data['text'])
            elif data.get('image_url'):
                message = service.send_image(recipient_id, data['image_url'])
            else:
                return Response(
                    {'error': 'No message content provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            return Response(
                InstagramMessageSerializer(message).data,
                status=status.HTTP_201_CREATED
            )
            
        except InstagramAPIError as e:
            error_code = getattr(e, 'code', None)
            error_subcode = getattr(e, 'subcode', None)
            
            logger.error(f"Instagram API error sending message: {e}", extra={
                'account_id': account_id,
                'conversation_id': conversation_id,
                'recipient_id': recipient_id,
                'error_code': error_code,
                'error_subcode': error_subcode,
                'error_details': getattr(e, 'details', None)
            })
            
            # Friendly error messages
            error_message = str(e)
            if error_code == 10 and error_subcode == 2534022:
                error_message = (
                    "Janela de 24 horas expirou. Você só pode responder mensagens "
                    "dentro de 24 horas após receber a última mensagem do usuário."
                )
            elif error_code == 10:
                error_message = f"Erro de permissão: {str(e)}"
            elif error_code == 100:
                error_message = f"Parâmetro inválido: {str(e)}"
            
            return Response(
                {
                    'error': error_message,
                    'code': error_code,
                    'subcode': error_subcode
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error sending Instagram message: {e}", exc_info=True, extra={
                'account_id': account_id,
                'conversation_id': conversation_id
            })
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def mark_seen(self, request):
        """Mark conversation as seen."""
        account_id = request.data.get('account_id')
        recipient_id = request.data.get('recipient_id')
        
        if not account_id or not recipient_id:
            return Response(
                {'error': 'account_id and recipient_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        account = get_object_or_404(
            InstagramAccount,
            id=account_id,
            owner=request.user
        )
        
        try:
            api = InstagramAPIService(account)
            api.mark_seen(recipient_id)
            return Response({'success': True})
        except InstagramAPIError as e:
            logger.error(f"Instagram mark_seen error: {e}", extra={
                'account_id': account_id,
                'recipient_id': recipient_id,
                'error_code': getattr(e, 'code', None)
            })
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def typing(self, request):
        """Send typing indicator.
        
        Note: Typing indicators may not be supported for Instagram Business accounts.
        Returns success=True even if not supported to avoid breaking the UI.
        """
        account_id = request.data.get('account_id')
        recipient_id = request.data.get('recipient_id')
        typing_on = request.data.get('typing_on', True)
        
        if not account_id or not recipient_id:
            return Response(
                {'error': 'account_id and recipient_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        account = get_object_or_404(
            InstagramAccount,
            id=account_id,
            owner=request.user
        )
        
        try:
            api = InstagramAPIService(account)
            result = api.send_typing_indicator(recipient_id, typing_on)
            
            # If not supported, still return success to avoid breaking UI
            if isinstance(result, dict) and result.get('success') is False:
                return Response({
                    'success': True,
                    'supported': False,
                    'message': 'Typing indicator not supported for this account'
                })
            
            return Response({'success': True, 'supported': True})
        except InstagramAPIError as e:
            # Log error but return success for code 1 (not supported)
            if e.code == 1:
                logger.warning(f'Instagram typing indicator not supported: {e}', extra={
                    'account_id': account_id,
                    'recipient_id': recipient_id
                })
                return Response({
                    'success': True,
                    'supported': False,
                    'message': 'Typing indicator not supported'
                })
            
            logger.error(f'Instagram typing indicator error: {e}', extra={
                'account_id': account_id,
                'recipient_id': recipient_id,
                'error_code': e.code if hasattr(e, 'code') else None
            })
            return Response({
                'error': str(e),
                'code': e.code if hasattr(e, 'code') else None
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f'Unexpected error in typing indicator: {e}', extra={
                'account_id': account_id,
                'recipient_id': recipient_id
            })
            # Return success to avoid breaking UI
            return Response({
                'success': True,
                'supported': False,
                'message': 'Feature not available'
            })


class InstagramWebhookView(APIView):
    """
    Webhook endpoint for Instagram.
    
    GET: Webhook verification (Meta verification challenge)
    POST: Receive webhook events
    """
    
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    
    def get(self, request):
        """Handle webhook verification from Meta."""
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        # Token fixo para verificação
        expected_token = 'pastita-ig-verify'
        
        logger.info(f"Instagram webhook verification: mode={mode}, token={token}, challenge={challenge}")
        
        if mode == 'subscribe' and token == expected_token:
            logger.info("Instagram webhook verified successfully")
            return HttpResponse(challenge, content_type='text/plain')
        
        logger.warning(f"Instagram webhook verification failed. mode={mode}, token={token}, expected={expected_token}")
        return Response(
            {'error': 'Verification failed'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    def post(self, request):
        """Handle incoming webhook events."""
        # Verify signature
        handler = InstagramWebhookHandler()
        signature = request.headers.get('X-Hub-Signature-256', '')
        
        if not handler.verify_signature(request.body, signature):
            logger.warning("Instagram webhook signature verification failed")
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Process webhook
        try:
            payload = request.data
            logger.info(f"Received Instagram webhook: {payload.get('object')}")
            
            result = handler.process_webhook(payload)
            
            logger.info(f"Processed Instagram webhook: {result['processed']} events, {result['errors']} errors")
            
            # Always return 200 to acknowledge receipt
            return Response({'status': 'ok'})
            
        except Exception as e:
            logger.error(f"Error processing Instagram webhook: {e}", exc_info=True)
            # Still return 200 to prevent Meta from retrying
            return Response({'status': 'error', 'message': str(e)})


class InstagramWebhookEventViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing webhook events (debugging)."""
    
    serializer_class = InstagramWebhookEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return InstagramWebhookEvent.objects.filter(
            account__owner=self.request.user
        ).order_by('-created_at')[:100]


class InstagramOAuthView(APIView):
    """
    OAuth flow for Instagram Business Login.
    
    GET /oauth/start/ - Start OAuth flow
    GET /oauth/callback/ - Handle OAuth callback
    """
    
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    
    INSTAGRAM_OAUTH_URL = "https://www.instagram.com/oauth/authorize"
    INSTAGRAM_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    GRAPH_API_URL = "https://graph.instagram.com"
    FACEBOOK_GRAPH_URL = "https://graph.facebook.com/v21.0"
    
    def get_redirect_uri(self, short=False):
        # Sem barra final - Meta é inconsistente com trailing slash
        if short:
            return f"{settings.API_BASE_URL}/ig/callback"
        return f"{settings.API_BASE_URL}/api/v1/instagram/oauth/callback"
    
    def get_app_credentials(self):
        return {
            'app_id': getattr(settings, 'INSTAGRAM_APP_ID', ''),
            'app_secret': getattr(settings, 'INSTAGRAM_APP_SECRET', ''),
        }


class InstagramOAuthStartView(InstagramOAuthView):
    """Start the Instagram OAuth flow."""
    
    def get(self, request):
        """Redirect user to Instagram authorization."""
        creds = self.get_app_credentials()
        
        if not creds['app_id']:
            return Response(
                {'error': 'Instagram App ID not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Check if using short URI (from /ig/start endpoint)
        use_short = request.path.startswith('/ig/')
        
        # Store state for CSRF protection
        import secrets
        state = secrets.token_urlsafe(32)
        request.session['instagram_oauth_state'] = state
        
        params = {
            'client_id': creds['app_id'],
            'redirect_uri': self.get_redirect_uri(short=use_short),
            'scope': 'instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights',
            'response_type': 'code',
            'state': state,
            'force_reauth': 'true',
        }
        
        auth_url = f"{self.INSTAGRAM_OAUTH_URL}?{urlencode(params)}"
        return redirect(auth_url)


class InstagramOAuthCallbackView(InstagramOAuthView):
    """Handle the Instagram OAuth callback."""
    
    def get(self, request):
        """Process OAuth callback and exchange code for token."""
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        error_description = request.query_params.get('error_description', '')
        
        # Check if using short URI (from /ig/callback endpoint)
        use_short = request.path.startswith('/ig/')
        
        # Dashboard URL for redirecting after OAuth
        dashboard_url = getattr(settings, 'DASHBOARD_URL', 'https://painel.pastita.com.br')
        
        if error:
            logger.error(f"Instagram OAuth error: {error} - {error_description}")
            return redirect(f"{dashboard_url}/instagram/accounts?error={error}&message={error_description}")
        
        if not code:
            return redirect(f"{dashboard_url}/instagram/accounts?error=no_code")
        
        creds = self.get_app_credentials()
        
        try:
            # Step 1: Exchange code for short-lived token
            token_response = requests.post(
                self.INSTAGRAM_TOKEN_URL,
                data={
                    'client_id': creds['app_id'],
                    'client_secret': creds['app_secret'],
                    'grant_type': 'authorization_code',
                    'redirect_uri': self.get_redirect_uri(short=use_short),
                    'code': code,
                }
            )
            
            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                return redirect(f"{dashboard_url}/instagram/accounts?error=token_exchange_failed")
            
            token_data = token_response.json()
            short_lived_token = token_data.get('access_token')
            user_id = token_data.get('user_id')
            
            # Step 2: Exchange for long-lived token
            long_lived_response = requests.get(
                f"{self.GRAPH_API_URL}/access_token",
                params={
                    'grant_type': 'ig_exchange_token',
                    'client_secret': creds['app_secret'],
                    'access_token': short_lived_token,
                }
            )
            
            if long_lived_response.status_code != 200:
                logger.error(f"Long-lived token exchange failed: {long_lived_response.text}")
                # Use short-lived token as fallback
                access_token = short_lived_token
                expires_in = 3600
            else:
                long_lived_data = long_lived_response.json()
                access_token = long_lived_data.get('access_token')
                expires_in = long_lived_data.get('expires_in', 5184000)  # 60 days
            
            # Step 3: Get Instagram Business Account info
            # First try to get from /me endpoint
            profile_response = requests.get(
                f"{self.GRAPH_API_URL}/me",
                params={
                    'fields': 'id,username,account_type,media_count,profile_picture_url,followers_count',
                    'access_token': access_token,
                }
            )
            
            profile_data = profile_response.json() if profile_response.status_code == 200 else {}
            logger.info(f"Instagram OAuth - /me response: {profile_data}")
            
            # If we got a username, use that data
            if profile_data.get('username'):
                username = profile_data.get('username')
                instagram_account_id = profile_data.get('id', str(user_id))
            else:
                # Fallback: Try to get Instagram Business Account from Facebook Pages
                # This requires pages_show_list and instagram_basic permissions
                logger.info("No username from /me, trying Facebook Pages API...")
                
                pages_response = requests.get(
                    f"{self.FACEBOOK_GRAPH_URL}/me/accounts",
                    params={
                        'fields': 'id,name,instagram_business_account{id,username,profile_picture_url,followers_count}',
                        'access_token': access_token,
                    }
                )
                
                pages_data = pages_response.json() if pages_response.status_code == 200 else {}
                logger.info(f"Instagram OAuth - Pages response: {pages_data}")
                
                # Find first page with Instagram Business Account
                instagram_account_id = str(user_id)
                username = f'user_{user_id}'
                facebook_page_id = ''
                
                for page in pages_data.get('data', []):
                    ig_account = page.get('instagram_business_account')
                    if ig_account:
                        instagram_account_id = ig_account.get('id', instagram_account_id)
                        username = ig_account.get('username', username)
                        facebook_page_id = page.get('id', '')
                        profile_data = {
                            'id': instagram_account_id,
                            'username': username,
                            'profile_picture_url': ig_account.get('profile_picture_url', ''),
                            'followers_count': ig_account.get('followers_count', 0),
                        }
                        logger.info(f"Found Instagram Business Account: @{username} (ID: {instagram_account_id})")
                        break
            
            logger.info(f"Instagram OAuth - Final profile: {profile_data}")
            
            # Step 4: CREATE OR UPDATE Instagram account in database
            from django.utils import timezone
            from datetime import timedelta
            from apps.core.models import User
            
            # Get or create a default owner (first superuser or first user)
            owner = User.objects.filter(is_superuser=True).first() or User.objects.first()
            
            if not owner:
                logger.error("No user found to assign Instagram account")
                return redirect(f"{dashboard_url}/instagram/accounts?error=no_user")
            
            # Calculate token expiration
            token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            # Get facebook_page_id if we found it
            fb_page_id = locals().get('facebook_page_id', '')
            
            # Create or update account
            account, created = InstagramAccount.objects.update_or_create(
                instagram_account_id=instagram_account_id,
                defaults={
                    'owner': owner,
                    'name': f'@{username}',
                    'username': username,
                    'instagram_user_id': str(user_id),
                    'facebook_page_id': fb_page_id,
                    'access_token': access_token,
                    'token_expires_at': token_expires_at,
                    'status': InstagramAccount.AccountStatus.ACTIVE,
                    'profile_picture_url': profile_data.get('profile_picture_url', ''),
                    'followers_count': profile_data.get('followers_count', 0),
                    'app_id': creds['app_id'],
                    'messaging_enabled': True,
                }
            )
            
            action = "created" if created else "updated"
            logger.info(f"Instagram account {action}: @{username} (ID: {account.id})")
            
            return redirect(
                f"{dashboard_url}/instagram/accounts?oauth_success=true&account_id={account.id}&username={username}"
            )
            
        except Exception as e:
            logger.error(f"Instagram OAuth error: {e}", exc_info=True)
            return redirect(f"{dashboard_url}/instagram/accounts?error=server_error&message={str(e)}")
