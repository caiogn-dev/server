"""
Instagram API Views.
"""
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

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
        """Set ice breakers for the account."""
        account = self.get_object()
        ice_breakers = request.data.get('ice_breakers', [])
        
        try:
            api = InstagramAPIService(account)
            result = api.set_ice_breakers(ice_breakers)
            return Response({'success': True, 'result': result})
        except InstagramAPIError as e:
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
        
        return queryset.select_related('account', 'conversation')
    
    def create(self, request, *args, **kwargs):
        """Send a new message."""
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        account_id = request.data.get('account_id')
        account = get_object_or_404(
            InstagramAccount, 
            id=account_id, 
            owner=request.user
        )
        
        service = InstagramMessageService(account)
        
        try:
            data = serializer.validated_data
            recipient_id = data['recipient_id']
            
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
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def mark_seen(self, request):
        """Mark conversation as seen."""
        account_id = request.data.get('account_id')
        recipient_id = request.data.get('recipient_id')
        
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def typing(self, request):
        """Send typing indicator."""
        account_id = request.data.get('account_id')
        recipient_id = request.data.get('recipient_id')
        typing_on = request.data.get('typing_on', True)
        
        account = get_object_or_404(
            InstagramAccount,
            id=account_id,
            owner=request.user
        )
        
        try:
            api = InstagramAPIService(account)
            api.send_typing_indicator(recipient_id, typing_on)
            return Response({'success': True})
        except InstagramAPIError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
        
        # Get expected verify token from settings or any active account
        from django.conf import settings
        expected_token = getattr(settings, 'INSTAGRAM_WEBHOOK_VERIFY_TOKEN', None)
        
        if not expected_token:
            # Try to find from any account
            account = InstagramAccount.objects.filter(
                webhook_verify_token__isnull=False
            ).exclude(webhook_verify_token='').first()
            
            if account:
                expected_token = account.webhook_verify_token
        
        if mode == 'subscribe' and token == expected_token:
            logger.info("Instagram webhook verified successfully")
            return HttpResponse(challenge, content_type='text/plain')
        
        logger.warning(f"Instagram webhook verification failed. Mode: {mode}, Token match: {token == expected_token}")
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
