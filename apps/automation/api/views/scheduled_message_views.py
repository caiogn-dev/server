"""
Scheduled Message API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta

from apps.automation.models import ScheduledMessage
from apps.automation.api.serializers import (
    ScheduledMessageSerializer,
    CreateScheduledMessageSerializer,
    UpdateScheduledMessageSerializer,
)
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class ScheduledMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for ScheduledMessage CRUD operations."""
    
    queryset = ScheduledMessage.objects.select_related('account', 'created_by').filter(is_active=True)
    serializer_class = ScheduledMessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's accounts
        if not user.is_superuser:
            queryset = queryset.filter(account__owner=user)
        
        # Filter by account
        account_id = self.request.query_params.get('account_id')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Filter by status
        msg_status = self.request.query_params.get('status')
        if msg_status:
            queryset = queryset.filter(status=msg_status)
        
        # Filter by message type
        message_type = self.request.query_params.get('message_type')
        if message_type:
            queryset = queryset.filter(message_type=message_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(scheduled_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(scheduled_at__lte=end_date)
        
        return queryset.order_by('scheduled_at')
    
    def create(self, request, *args, **kwargs):
        """Create a new scheduled message."""
        serializer = CreateScheduledMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        account_id = data.pop('account_id')
        
        from apps.whatsapp.models import WhatsAppAccount
        try:
            account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            return Response(
                {'error': 'WhatsApp account not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        scheduled_message = ScheduledMessage.objects.create(
            account=account,
            created_by=request.user,
            **data
        )
        
        return Response(
            ScheduledMessageSerializer(scheduled_message).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a scheduled message."""
        instance = self.get_object()
        
        # Can only update pending messages
        if instance.status != ScheduledMessage.Status.PENDING:
            return Response(
                {'error': 'Can only update pending messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = UpdateScheduledMessageSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        for key, value in serializer.validated_data.items():
            setattr(instance, key, value)
        
        instance.save()
        return Response(ScheduledMessageSerializer(instance).data)
    
    def destroy(self, request, *args, **kwargs):
        """Cancel a scheduled message."""
        instance = self.get_object()
        
        if instance.status == ScheduledMessage.Status.PENDING:
            instance.status = ScheduledMessage.Status.CANCELLED
            instance.save(update_fields=['status'])
        else:
            instance.is_active = False
            instance.save(update_fields=['is_active'])
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending scheduled message."""
        instance = self.get_object()
        
        if instance.status != ScheduledMessage.Status.PENDING:
            return Response(
                {'error': 'Can only cancel pending messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.status = ScheduledMessage.Status.CANCELLED
        instance.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Scheduled message cancelled'
        })
    
    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Reschedule a message."""
        instance = self.get_object()
        new_scheduled_at = request.data.get('scheduled_at')
        
        if not new_scheduled_at:
            return Response(
                {'error': 'scheduled_at is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if instance.status not in [ScheduledMessage.Status.PENDING, ScheduledMessage.Status.FAILED]:
            return Response(
                {'error': 'Can only reschedule pending or failed messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.utils.dateparse import parse_datetime
        parsed_date = parse_datetime(new_scheduled_at)
        if not parsed_date:
            return Response(
                {'error': 'Invalid datetime format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.scheduled_at = parsed_date
        instance.status = ScheduledMessage.Status.PENDING
        instance.error_message = ''
        instance.save()
        
        return Response(ScheduledMessageSerializer(instance).data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get scheduled message statistics."""
        account_id = request.query_params.get('account_id')
        
        queryset = self.get_queryset()
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return Response({
            'total': queryset.count(),
            'pending': queryset.filter(status=ScheduledMessage.Status.PENDING).count(),
            'sent': queryset.filter(status=ScheduledMessage.Status.SENT).count(),
            'failed': queryset.filter(status=ScheduledMessage.Status.FAILED).count(),
            'cancelled': queryset.filter(status=ScheduledMessage.Status.CANCELLED).count(),
            'scheduled_today': queryset.filter(
                status=ScheduledMessage.Status.PENDING,
                scheduled_at__gte=today_start,
                scheduled_at__lt=today_start + timedelta(days=1)
            ).count(),
            'sent_today': queryset.filter(
                status=ScheduledMessage.Status.SENT,
                sent_at__gte=today_start
            ).count(),
        })
