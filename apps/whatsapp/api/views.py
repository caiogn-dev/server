"""
WhatsApp API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from ..models import WhatsAppAccount, Message, MessageTemplate
from ..services import MessageService, WhatsAppAPIService
from ..repositories import WhatsAppAccountRepository, MessageRepository
from .serializers import (
    WhatsAppAccountSerializer,
    WhatsAppAccountCreateSerializer,
    WhatsAppAccountUpdateSerializer,
    MessageSerializer,
    SendTextMessageSerializer,
    SendTemplateMessageSerializer,
    SendInteractiveButtonsSerializer,
    SendInteractiveListSerializer,
    SendImageSerializer,
    SendDocumentSerializer,
    MessageTemplateSerializer,
    MarkAsReadSerializer,
    ConversationHistorySerializer,
    MessageStatsSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List WhatsApp accounts"),
    retrieve=extend_schema(summary="Get WhatsApp account details"),
    create=extend_schema(summary="Create WhatsApp account"),
    update=extend_schema(summary="Update WhatsApp account"),
    partial_update=extend_schema(summary="Partial update WhatsApp account"),
    destroy=extend_schema(summary="Delete WhatsApp account"),
)
class WhatsAppAccountViewSet(viewsets.ModelViewSet):
    """ViewSet for WhatsApp Account management."""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'is_active']

    def get_queryset(self):
        return WhatsAppAccount.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action == 'create':
            return WhatsAppAccountCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return WhatsAppAccountUpdateSerializer
        return WhatsAppAccountSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.status = WhatsAppAccount.AccountStatus.INACTIVE
        instance.save()

    @extend_schema(summary="Force delete WhatsApp account and all related data")
    @action(detail=True, methods=['delete'])
    def force_delete(self, request, pk=None):
        """
        Force delete a WhatsApp account and all related data.
        
        This will delete:
        - All messages
        - All webhook events
        - All conversations
        - All campaigns and recipients
        - All scheduled messages
        - All automation sessions
        - All orders
        - All payments
        - All langflow integrations
        - The account itself
        """
        from django.db import transaction
        
        account = self.get_object()
        account_id = str(account.id)
        account_name = account.name
        
        deleted_counts = {}
        
        try:
            with transaction.atomic():
                # Delete messages
                deleted_counts['messages'] = account.messages.count()
                account.messages.all().delete()
                
                # Delete webhook events
                deleted_counts['webhook_events'] = account.webhook_events.count()
                account.webhook_events.all().delete()
                
                # Delete templates
                deleted_counts['templates'] = account.templates.count()
                account.templates.all().delete()
                
                # Delete conversations
                try:
                    from apps.conversations.models import Conversation
                    conversations = Conversation.objects.filter(account=account)
                    deleted_counts['conversations'] = conversations.count()
                    conversations.delete()
                except Exception as e:
                    logger.warning(f"Could not delete conversations: {e}")
                    deleted_counts['conversations'] = 0
                
                # Delete campaigns and related
                try:
                    from apps.campaigns.models import Campaign, ScheduledMessage, ContactList
                    campaigns = Campaign.objects.filter(account=account)
                    for campaign in campaigns:
                        campaign.recipients.all().delete()
                    deleted_counts['campaigns'] = campaigns.count()
                    campaigns.delete()
                    
                    scheduled = ScheduledMessage.objects.filter(account=account)
                    deleted_counts['scheduled_messages'] = scheduled.count()
                    scheduled.delete()
                    
                    contact_lists = ContactList.objects.filter(account=account)
                    deleted_counts['contact_lists'] = contact_lists.count()
                    contact_lists.delete()
                except Exception as e:
                    logger.warning(f"Could not delete campaigns: {e}")
                    deleted_counts['campaigns'] = 0
                
                # Delete automation sessions
                try:
                    from apps.automation.models import AutomationSession
                    sessions = AutomationSession.objects.filter(account=account)
                    deleted_counts['automation_sessions'] = sessions.count()
                    sessions.delete()
                except Exception as e:
                    logger.warning(f"Could not delete automation sessions: {e}")
                    deleted_counts['automation_sessions'] = 0
                
                # Delete orders
                try:
                    from apps.orders.models import Order
                    orders = Order.objects.filter(account=account)
                    deleted_counts['orders'] = orders.count()
                    orders.delete()
                except Exception as e:
                    logger.warning(f"Could not delete orders: {e}")
                    deleted_counts['orders'] = 0
                
                # Delete payments
                try:
                    from apps.payments.models import Payment
                    payments = Payment.objects.filter(account=account)
                    deleted_counts['payments'] = payments.count()
                    payments.delete()
                except Exception as e:
                    logger.warning(f"Could not delete payments: {e}")
                    deleted_counts['payments'] = 0
                
                # Delete langflow integrations
                try:
                    from apps.langflow.models import LangflowIntegration
                    integrations = LangflowIntegration.objects.filter(account=account)
                    deleted_counts['langflow_integrations'] = integrations.count()
                    integrations.delete()
                except Exception as e:
                    logger.warning(f"Could not delete langflow integrations: {e}")
                    deleted_counts['langflow_integrations'] = 0
                
                # Finally delete the account
                account.delete()
                
            logger.info(f"Force deleted WhatsApp account {account_name} ({account_id}): {deleted_counts}")
            
            return Response({
                'status': 'deleted',
                'account_id': account_id,
                'account_name': account_name,
                'deleted_counts': deleted_counts
            })
            
        except Exception as e:
            logger.error(f"Error force deleting account {account_id}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(summary="Activate WhatsApp account")
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a WhatsApp account."""
        account = self.get_object()
        account.status = WhatsAppAccount.AccountStatus.ACTIVE
        account.save()
        return Response(WhatsAppAccountSerializer(account).data)

    @extend_schema(summary="Deactivate WhatsApp account")
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a WhatsApp account."""
        account = self.get_object()
        account.status = WhatsAppAccount.AccountStatus.INACTIVE
        account.save()
        return Response(WhatsAppAccountSerializer(account).data)

    @extend_schema(summary="Rotate access token")
    @action(detail=True, methods=['post'])
    def rotate_token(self, request, pk=None):
        """Rotate the access token for an account."""
        account = self.get_object()
        new_token = request.data.get('access_token')
        
        if not new_token:
            return Response(
                {'error': 'access_token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        account.rotate_token(new_token)
        return Response({
            'message': 'Token rotated successfully',
            'token_version': account.token_version
        })

    @extend_schema(summary="Get business profile")
    @action(detail=True, methods=['get'])
    def business_profile(self, request, pk=None):
        """Get business profile for an account."""
        account = self.get_object()
        api_service = WhatsAppAPIService(account)
        
        try:
            profile = api_service.get_business_profile()
            return Response(profile)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )

    @extend_schema(summary="Sync message templates")
    @action(detail=True, methods=['post'])
    def sync_templates(self, request, pk=None):
        """Sync message templates from WhatsApp."""
        account = self.get_object()
        api_service = WhatsAppAPIService(account)
        
        try:
            templates_data = api_service.get_templates()
            templates = templates_data.get('data', [])
            
            synced = 0
            for template_data in templates:
                MessageTemplate.objects.update_or_create(
                    account=account,
                    template_id=template_data.get('id'),
                    defaults={
                        'name': template_data.get('name'),
                        'language': template_data.get('language'),
                        'category': template_data.get('category', 'utility').lower(),
                        'status': template_data.get('status', 'pending').lower(),
                        'components': template_data.get('components', []),
                    }
                )
                synced += 1
            
            return Response({
                'message': f'Synced {synced} templates',
                'count': synced
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )


@extend_schema_view(
    list=extend_schema(summary="List messages"),
    retrieve=extend_schema(summary="Get message details"),
)
class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Message operations."""
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'direction', 'status', 'message_type']

    def get_queryset(self):
        return Message.objects.select_related('account', 'conversation').all()

    @extend_schema(
        summary="Send text message",
        request=SendTextMessageSerializer,
        responses={201: MessageSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_text(self, request):
        """Send a text message."""
        serializer = SendTextMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        message = service.send_text_message(**serializer.validated_data)
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Send template message",
        request=SendTemplateMessageSerializer,
        responses={201: MessageSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_template(self, request):
        """Send a template message."""
        serializer = SendTemplateMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        message = service.send_template_message(**serializer.validated_data)
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Send interactive buttons message",
        request=SendInteractiveButtonsSerializer,
        responses={201: MessageSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_interactive_buttons(self, request):
        """Send an interactive buttons message."""
        serializer = SendInteractiveButtonsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        message = service.send_interactive_buttons(**serializer.validated_data)
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Send interactive list message",
        request=SendInteractiveListSerializer,
        responses={201: MessageSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_interactive_list(self, request):
        """Send an interactive list message."""
        serializer = SendInteractiveListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        message = service.send_interactive_list(**serializer.validated_data)
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Send image message",
        request=SendImageSerializer,
        responses={201: MessageSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_image(self, request):
        """Send an image message."""
        serializer = SendImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        message = service.send_image(**serializer.validated_data)
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Send document message",
        request=SendDocumentSerializer,
        responses={201: MessageSerializer}
    )
    @action(detail=False, methods=['post'])
    def send_document(self, request):
        """Send a document message."""
        serializer = SendDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        message = service.send_document(**serializer.validated_data)
        
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Mark message as read",
        request=MarkAsReadSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def mark_as_read(self, request):
        """Mark a message as read."""
        serializer = MarkAsReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        success = service.mark_as_read(
            account_id=str(serializer.validated_data['account_id']),
            message_id=serializer.validated_data['message_id']
        )
        
        return Response({'success': success})

    @extend_schema(
        summary="Get conversation history",
        request=ConversationHistorySerializer,
        responses={200: MessageSerializer(many=True)}
    )
    @action(detail=False, methods=['post'])
    def conversation_history(self, request):
        """Get conversation history with a phone number."""
        serializer = ConversationHistorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        messages = service.get_conversation_history(
            account_id=str(serializer.validated_data['account_id']),
            phone_number=serializer.validated_data['phone_number'],
            limit=serializer.validated_data.get('limit', 50)
        )
        
        return Response(MessageSerializer(messages, many=True).data)

    @extend_schema(
        summary="Get message statistics",
        request=MessageStatsSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def stats(self, request):
        """Get message statistics."""
        serializer = MessageStatsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = MessageService()
        stats = service.get_message_stats(
            account_id=str(serializer.validated_data['account_id']),
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data['end_date']
        )
        
        return Response(stats)


@extend_schema_view(
    list=extend_schema(summary="List message templates"),
    retrieve=extend_schema(summary="Get message template details"),
)
class MessageTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Message Template operations."""
    serializer_class = MessageTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'status', 'category']

    def get_queryset(self):
        return MessageTemplate.objects.select_related('account').filter(is_active=True)
