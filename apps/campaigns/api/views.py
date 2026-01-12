"""
Campaign API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from ..models import Campaign, CampaignRecipient, ScheduledMessage, ContactList
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
            return Response(CampaignSerializer(campaign).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Pause campaign")
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a running campaign."""
        service = CampaignService()
        try:
            campaign = service.pause_campaign(str(pk))
            return Response(CampaignSerializer(campaign).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Resume campaign")
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a paused campaign."""
        service = CampaignService()
        try:
            campaign = service.resume_campaign(str(pk))
            return Response(CampaignSerializer(campaign).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Cancel campaign")
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a campaign."""
        service = CampaignService()
        try:
            campaign = service.cancel_campaign(str(pk))
            return Response(CampaignSerializer(campaign).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Get campaign statistics")
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get campaign statistics."""
        service = CampaignService()
        stats = service.get_campaign_stats(str(pk))
        return Response(stats)
    
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
