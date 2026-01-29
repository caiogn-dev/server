"""
Campaign API views.
"""
import logging
import traceback
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.db.models import Max
from django.utils import timezone

from ..models import Campaign, CampaignRecipient, ContactList
from apps.automation.models import ScheduledMessage  # Use unified model
from ..services import CampaignService, SchedulerService
from .serializers import (
    CampaignSerializer,
    CampaignCreateSerializer,
    CampaignRecipientSerializer,
    AddRecipientsSerializer,
    ScheduledMessageSerializer,
    ScheduledMessageCreateSerializer,
    ContactListSerializer,
    ContactListCreateSerializer,
    ImportContactsSerializer,
)

logger = logging.getLogger(__name__)


class SystemContactsView(APIView):
    """
    Get contacts from the system (conversations, orders, subscribers).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get system contacts",
        description="Fetch contacts from conversations, orders, and subscribers",
        parameters=[
            {
                'name': 'account_id',
                'in': 'query',
                'description': 'WhatsApp account ID to filter contacts',
                'required': False,
                'schema': {'type': 'string'}
            },
            {
                'name': 'source',
                'in': 'query',
                'description': 'Source filter: all, conversations, orders, subscribers',
                'required': False,
                'schema': {'type': 'string', 'default': 'all'}
            },
            {
                'name': 'limit',
                'in': 'query',
                'description': 'Maximum number of contacts to return',
                'required': False,
                'schema': {'type': 'integer', 'default': 100}
            }
        ]
    )
    def get(self, request):
        account_id = request.query_params.get('account_id')
        source = request.query_params.get('source', 'all')
        limit = int(request.query_params.get('limit', 100))
        
        contacts = {}  # Use dict to deduplicate by phone
        
        # Get contacts from conversations
        if source in ['all', 'conversations']:
            try:
                from apps.conversations.models import Conversation
                conv_qs = Conversation.objects.all()
                if account_id:
                    conv_qs = conv_qs.filter(account_id=account_id)
                
                conversations = conv_qs.values(
                    'phone_number', 'contact_name'
                ).annotate(
                    last_activity=Max('updated_at')
                ).order_by('-last_activity')[:limit]
                
                for conv in conversations:
                    phone = conv['phone_number']
                    if phone and phone not in contacts:
                        contacts[phone] = {
                            'phone': phone,
                            'name': conv['contact_name'] or '',
                            'source': 'conversation'
                        }
            except Exception as e:
                logger.warning(f"Error fetching conversations: {e}")
        
        # Get contacts from orders
        if source in ['all', 'orders']:
            try:
                from apps.orders.models import Order
                orders = Order.objects.values(
                    'customer_phone', 'customer_name'
                ).annotate(
                    last_order=Max('created_at')
                ).order_by('-last_order')[:limit]
                
                for order in orders:
                    phone = order['customer_phone']
                    if phone and phone not in contacts:
                        contacts[phone] = {
                            'phone': phone,
                            'name': order['customer_name'] or '',
                            'source': 'order'
                        }
            except Exception as e:
                logger.warning(f"Error fetching orders: {e}")
        
        # Get contacts from marketing subscribers
        if source in ['all', 'subscribers']:
            try:
                from apps.marketing.models import Subscriber
                subscribers = Subscriber.objects.filter(
                    phone__isnull=False
                ).exclude(
                    phone=''
                ).values(
                    'phone', 'name', 'email'
                ).order_by('-created_at')[:limit]
                
                for sub in subscribers:
                    phone = sub['phone']
                    if phone and phone not in contacts:
                        name = sub['name'] or sub['email'] or ''
                        contacts[phone] = {
                            'phone': phone,
                            'name': name,
                            'source': 'subscriber'
                        }
            except Exception as e:
                logger.warning(f"Error fetching subscribers: {e}")
        
        # Get contacts from automation sessions
        if source in ['all', 'sessions']:
            try:
                from apps.automation.models import CustomerSession
                sessions_qs = CustomerSession.objects.all()
                if account_id:
                    # CustomerSession has company -> CompanyProfile has account
                    sessions_qs = sessions_qs.filter(company__account_id=account_id)
                
                sessions = sessions_qs.values(
                    'phone_number', 'customer_name'
                ).annotate(
                    last_activity=Max('updated_at')
                ).order_by('-last_activity')[:limit]
                
                for session in sessions:
                    phone = session['phone_number']
                    if phone and phone not in contacts:
                        contacts[phone] = {
                            'phone': phone,
                            'name': session['customer_name'] or '',
                            'source': 'session'
                        }
            except Exception as e:
                logger.warning(f"Error fetching sessions: {e}")
        
        # Convert to list and limit
        contact_list = list(contacts.values())[:limit]
        
        return Response({
            'count': len(contact_list),
            'results': contact_list
        })


@extend_schema_view(
    list=extend_schema(summary="List campaigns"),
    retrieve=extend_schema(summary="Get campaign details"),
)
class CampaignViewSet(viewsets.ModelViewSet):
    """ViewSet for Campaign management."""
    serializer_class = CampaignSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'status', 'campaign_type']
    
    def get_queryset(self):
        return Campaign.objects.filter(is_active=True)
    
    @extend_schema(
        summary="Create campaign",
        request=CampaignCreateSerializer,
        responses={201: CampaignSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new campaign."""
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = CampaignService()
        campaign = service.create_campaign(
            **serializer.validated_data,
            created_by=request.user
        )
        
        return Response(
            CampaignSerializer(campaign).data,
            status=status.HTTP_201_CREATED
        )
    
    @extend_schema(summary="Schedule campaign")
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Schedule a campaign."""
        scheduled_at = request.data.get('scheduled_at')
        if not scheduled_at:
            return Response(
                {'error': 'scheduled_at is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = CampaignService()
        try:
            from django.utils.dateparse import parse_datetime
            scheduled_at = parse_datetime(scheduled_at)
            campaign = service.schedule_campaign(str(pk), scheduled_at)
            return Response(CampaignSerializer(campaign).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Start campaign")
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a campaign immediately."""
        service = CampaignService()
        try:
            campaign = service.start_campaign(str(pk))
            logger.info(f"Campaign {pk} started successfully by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            logger.warning(f"Campaign {pk} not found")
            return Response(
                {'error': 'Campanha não encontrada'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            logger.warning(f"Campaign {pk} start validation failed: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} start error: {e}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Erro ao iniciar campanha. Verifique se o serviço de filas está ativo.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(summary="Pause campaign")
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a running campaign."""
        service = CampaignService()
        try:
            campaign = service.pause_campaign(str(pk))
            logger.info(f"Campaign {pk} paused by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} pause error: {e}\n{traceback.format_exc()}")
            return Response({'error': 'Erro ao pausar campanha'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Resume campaign")
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a paused campaign."""
        service = CampaignService()
        try:
            campaign = service.resume_campaign(str(pk))
            logger.info(f"Campaign {pk} resumed by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} resume error: {e}\n{traceback.format_exc()}")
            return Response({'error': 'Erro ao retomar campanha'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Cancel campaign")
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a campaign."""
        service = CampaignService()
        try:
            campaign = service.cancel_campaign(str(pk))
            logger.info(f"Campaign {pk} cancelled by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} cancel error: {e}\n{traceback.format_exc()}")
            return Response({'error': 'Erro ao cancelar campanha'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(summary="Get campaign statistics")
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get campaign statistics."""
        service = CampaignService()
        stats = service.get_campaign_stats(str(pk))
        return Response(stats)
    
    @extend_schema(summary="Force process campaign batch")
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """
        Force process a campaign batch synchronously.
        Use this when Celery is not available or campaign is stuck.
        """
        service = CampaignService()
        try:
            campaign = Campaign.objects.get(id=pk)
            
            # If campaign is not running, start it first
            if campaign.status in [Campaign.CampaignStatus.DRAFT, Campaign.CampaignStatus.SCHEDULED]:
                campaign.status = Campaign.CampaignStatus.RUNNING
                campaign.started_at = timezone.now()
                campaign.save()
                logger.info(f"Campaign {pk} status changed to running")
            
            if campaign.status != Campaign.CampaignStatus.RUNNING:
                return Response(
                    {'error': f'Campaign cannot be processed (status: {campaign.status})'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Process batch
            batch_size = int(request.data.get('batch_size', 50))
            result = service.process_campaign_batch(str(pk), batch_size=batch_size)
            
            logger.info(f"Campaign {pk} processed: {result}")
            
            return Response({
                'success': True,
                'processed': result.get('processed', 0),
                'failed': result.get('failed', 0),
                'remaining': result.get('remaining', 0),
                'campaign_status': Campaign.objects.get(id=pk).status,
            })
            
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Campaign {pk} process error: {e}\n{traceback.format_exc()}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(summary="Get campaign recipients")
    @action(detail=True, methods=['get'])
    def recipients(self, request, pk=None):
        """Get campaign recipients."""
        campaign = self.get_object()
        recipients = campaign.recipients.all()
        
        status_filter = request.query_params.get('status')
        if status_filter:
            recipients = recipients.filter(status=status_filter)
        
        serializer = CampaignRecipientSerializer(recipients[:100], many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Add recipients",
        request=AddRecipientsSerializer,
    )
    @action(detail=True, methods=['post'])
    def add_recipients(self, request, pk=None):
        """Add recipients to a campaign."""
        serializer = AddRecipientsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = CampaignService()
        try:
            count = service.add_recipients(str(pk), serializer.validated_data['contacts'])
            return Response({'added': count})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(summary="List scheduled messages"),
    retrieve=extend_schema(summary="Get scheduled message details"),
)
class ScheduledMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for ScheduledMessage management."""
    serializer_class = ScheduledMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'status', 'message_type']
    
    def get_queryset(self):
        return ScheduledMessage.objects.filter(is_active=True)
    
    @extend_schema(
        summary="Create scheduled message",
        request=ScheduledMessageCreateSerializer,
        responses={201: ScheduledMessageSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new scheduled message."""
        serializer = ScheduledMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = SchedulerService()
        try:
            message = service.schedule_message(
                **serializer.validated_data,
                created_by=request.user
            )
            return Response(
                ScheduledMessageSerializer(message).data,
                status=status.HTTP_201_CREATED
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Cancel scheduled message")
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a scheduled message."""
        service = SchedulerService()
        try:
            message = service.cancel_scheduled_message(str(pk))
            return Response(ScheduledMessageSerializer(message).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Get scheduled messages statistics")
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get scheduled messages statistics."""
        account_id = request.query_params.get('account_id')
        service = SchedulerService()
        stats = service.get_scheduled_messages_stats(account_id)
        return Response(stats)


@extend_schema_view(
    list=extend_schema(summary="List contact lists"),
    retrieve=extend_schema(summary="Get contact list details"),
)
class ContactListViewSet(viewsets.ModelViewSet):
    """ViewSet for ContactList management."""
    serializer_class = ContactListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'source']
    
    def get_queryset(self):
        return ContactList.objects.filter(is_active=True)
    
    @extend_schema(
        summary="Create contact list",
        request=ContactListCreateSerializer,
        responses={201: ContactListSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new contact list."""
        serializer = ContactListCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = CampaignService()
        contact_list = service.create_contact_list(
            **serializer.validated_data,
            created_by=request.user
        )
        
        return Response(
            ContactListSerializer(contact_list).data,
            status=status.HTTP_201_CREATED
        )
    
    @extend_schema(
        summary="Import contacts from CSV",
        request=ImportContactsSerializer,
        responses={201: ContactListSerializer}
    )
    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """Import contacts from CSV."""
        serializer = ImportContactsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = CampaignService()
        contact_list = service.import_contacts_from_csv(
            account_id=str(serializer.validated_data['account_id']),
            name=serializer.validated_data['name'],
            csv_content=serializer.validated_data['csv_content'],
            created_by=request.user
        )
        
        return Response(
            ContactListSerializer(contact_list).data,
            status=status.HTTP_201_CREATED
        )
