"""
ViewSets for unified messaging models.

These ViewSets provide a unified API for all messaging platforms.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend

from apps.messaging.models import (
    PlatformAccount,
    UnifiedConversation,
    UnifiedMessage,
    UnifiedTemplate,
)
from .serializers_unified import (
    PlatformAccountSerializer,
    PlatformAccountCreateSerializer,
    PlatformAccountUpdateSerializer,
    UnifiedConversationSerializer,
    UnifiedMessageSerializer,
    UnifiedMessageCreateSerializer,
    UnifiedTemplateSerializer,
    UnifiedTemplateCreateSerializer,
)


class PlatformAccountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for unified PlatformAccount.
    
    Provides CRUD operations for all messaging platform accounts
    (WhatsApp, Instagram, Messenger) in a single endpoint.
    
    list: GET /api/v1/messaging/accounts/
    create: POST /api/v1/messaging/accounts/
    retrieve: GET /api/v1/messaging/accounts/{id}/
    update: PUT /api/v1/messaging/accounts/{id}/
    partial_update: PATCH /api/v1/messaging/accounts/{id}/
    destroy: DELETE /api/v1/messaging/accounts/{id}/
    """
    
    queryset = PlatformAccount.objects.all()
    serializer_class = PlatformAccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['platform', 'status', 'is_active', 'is_verified']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter accounts by current user."""
        return self.queryset.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return PlatformAccountCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PlatformAccountUpdateSerializer
        return PlatformAccountSerializer
    
    def perform_create(self, serializer):
        """Set user on creation."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """
        Sync account information from platform.
        
        POST /api/v1/messaging/accounts/{id}/sync/
        """
        account = self.get_object()
        
        try:
            # Platform-specific sync logic
            if account.is_whatsapp:
                from apps.whatsapp.services import WhatsAppService
                service = WhatsAppService(account)
                info = service.get_account_info()
            elif account.is_instagram:
                from apps.instagram.services import InstagramService
                service = InstagramService(account)
                info = service.get_account_info()
            elif account.is_messenger:
                from apps.messaging.services import MessengerService
                service = MessengerService(account)
                info = service.get_page_info()
            else:
                return Response(
                    {'error': 'Unknown platform'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update account with synced info
            account.metadata.update(info)
            account.last_sync_at = __import__('django.utils.timezone').now()
            account.save()
            
            return Response({
                'status': 'success',
                'data': info
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def verify_webhook(self, request, pk=None):
        """
        Verify webhook for this account.
        
        POST /api/v1/messaging/accounts/{id}/verify_webhook/
        """
        account = self.get_object()
        
        try:
            account.webhook_verified = True
            account.save()
            
            return Response({'status': 'verified'})
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def rotate_token(self, request, pk=None):
        """
        Rotate access token.
        
        POST /api/v1/messaging/accounts/{id}/rotate_token/
        {
            "new_token": "..."
        }
        """
        account = self.get_object()
        new_token = request.data.get('new_token')
        
        if not new_token:
            return Response(
                {'error': 'new_token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            account.rotate_token(new_token)
            return Response({
                'status': 'success',
                'token_version': account.token_version
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get account statistics.
        
        GET /api/v1/messaging/accounts/stats/
        """
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'by_platform': {
                'whatsapp': queryset.filter(platform='whatsapp').count(),
                'instagram': queryset.filter(platform='instagram').count(),
                'messenger': queryset.filter(platform='messenger').count(),
            },
            'by_status': {
                'active': queryset.filter(status='active').count(),
                'pending': queryset.filter(status='pending').count(),
                'error': queryset.filter(status='error').count(),
            },
            'verified': queryset.filter(is_verified=True).count(),
        }
        
        return Response(stats)


class UnifiedConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for unified conversations.
    
    list: GET /api/v1/messaging/conversations/
    retrieve: GET /api/v1/messaging/conversations/{id}/
    """
    
    queryset = UnifiedConversation.objects.all()
    serializer_class = UnifiedConversationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['platform', 'status', 'is_active', 'assigned_to']
    ordering_fields = ['last_message_at', 'created_at', 'unread_count']
    ordering = ['-last_message_at']
    search_fields = ['customer_name', 'customer_phone']
    
    def get_queryset(self):
        """Filter conversations by user's platform accounts."""
        user_accounts = PlatformAccount.objects.filter(user=self.request.user)
        return self.queryset.filter(platform_account__in=user_accounts)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark conversation as read."""
        conversation = self.get_object()
        conversation.mark_read()
        return Response({'status': 'marked_as_read'})
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """
        Assign conversation to user.
        
        POST /api/v1/messaging/conversations/{id}/assign/
        {
            "user_id": "..."
        }
        """
        conversation = self.get_object()
        user_id = request.data.get('user_id')
        
        if user_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = get_object_or_404(User, id=user_id)
            conversation.assign_to(user)
        else:
            conversation.unassign()
        
        return Response({'status': 'assigned' if user_id else 'unassigned'})
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """
        Get messages for conversation.
        
        GET /api/v1/messaging/conversations/{id}/messages/
        """
        conversation = self.get_object()
        messages = conversation.messages.all()
        
        # Pagination
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = UnifiedMessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = UnifiedMessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """
        Send message in conversation.
        
        POST /api/v1/messaging/conversations/{id}/send_message/
        {
            "text": "Hello",
            "type": "text"
        }
        """
        conversation = self.get_object()
        text = request.data.get('text')
        message_type = request.data.get('type', 'text')
        
        if not text:
            return Response(
                {'error': 'text is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Create message
            message = UnifiedMessage.objects.create(
                conversation=conversation,
                platform_account=conversation.platform_account,
                platform=conversation.platform,
                direction=UnifiedMessage.Direction.OUTBOUND,
                message_type=message_type,
                text_body=text,
                status=UnifiedMessage.Status.PENDING,
            )
            
            # Send via appropriate service
            if conversation.is_whatsapp:
                from apps.whatsapp.services import WhatsAppService
                service = WhatsAppService(conversation.platform_account)
                result = service.send_message(conversation.customer_phone, text)
            elif conversation.is_instagram:
                from apps.instagram.services import InstagramService
                service = InstagramService(conversation.platform_account)
                result = service.send_message(conversation.customer_platform_id, text)
            elif conversation.is_messenger:
                from apps.messaging.services import MessengerService
                service = MessengerService(conversation.platform_account)
                result = service.send_text_message(conversation.psid, text)
            else:
                return Response(
                    {'error': 'Unknown platform'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update message status
            message.mark_sent(result.get('message_id'))
            
            return Response({
                'status': 'sent',
                'message_id': str(message.id),
                'external_id': message.external_id,
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class UnifiedMessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for unified messages.
    
    list: GET /api/v1/messaging/messages/
    retrieve: GET /api/v1/messaging/messages/{id}/
    """
    
    queryset = UnifiedMessage.objects.all()
    serializer_class = UnifiedMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['platform', 'direction', 'status', 'message_type', 'conversation']
    ordering_fields = ['created_at', 'sent_at', 'delivered_at', 'read_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter messages by user's platform accounts."""
        user_accounts = PlatformAccount.objects.filter(user=self.request.user)
        return self.queryset.filter(platform_account__in=user_accounts)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UnifiedMessageCreateSerializer
        return UnifiedMessageSerializer


class UnifiedTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for unified templates.
    
    list: GET /api/v1/messaging/templates/
    create: POST /api/v1/messaging/templates/
    retrieve: GET /api/v1/messaging/templates/{id}/
    update: PUT /api/v1/messaging/templates/{id}/
    destroy: DELETE /api/v1/messaging/templates/{id}/
    """
    
    queryset = UnifiedTemplate.objects.all()
    serializer_class = UnifiedTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['platform', 'status', 'category', 'language', 'is_active']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']
    search_fields = ['name', 'body']
    
    def get_queryset(self):
        """Filter templates by user's platform accounts or store."""
        user_accounts = PlatformAccount.objects.filter(user=self.request.user)
        return self.queryset.filter(platform_account__in=user_accounts)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UnifiedTemplateCreateSerializer
        return UnifiedTemplateSerializer
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """
        Submit template for approval (WhatsApp).
        
        POST /api/v1/messaging/templates/{id}/submit/
        """
        template = self.get_object()
        
        try:
            if template.platform == 'whatsapp':
                from apps.whatsapp.services import WhatsAppService
                service = WhatsAppService(template.platform_account)
                result = service.submit_template(template)
                
                template.mark_submitted()
                
                return Response({
                    'status': 'submitted',
                    'result': result
                })
            else:
                return Response(
                    {'error': 'Submission only supported for WhatsApp'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def render(self, request, pk=None):
        """
        Render template with variables.
        
        POST /api/v1/messaging/templates/{id}/render/
        {
            "variables": {"name": "John", "order_id": "123"}
        }
        """
        template = self.get_object()
        variables = request.data.get('variables', {})
        
        rendered = template.render(variables)
        
        return Response({
            'rendered': rendered,
            'variables_used': list(variables.keys())
        })
