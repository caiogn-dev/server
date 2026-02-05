"""
Customer Session API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from apps.automation.models import CustomerSession
from apps.automation.services import AutomationService
from apps.automation.api.serializers import CustomerSessionSerializer
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class CustomerSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for CustomerSession (read-only with actions)."""
    
    queryset = CustomerSession.objects.select_related('company', 'company__store', 'company__account', 'conversation', 'order').filter(is_active=True)
    serializer_class = CustomerSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's stores or accounts
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(company__store__owner=user) | 
                Q(company__store__staff=user) | 
                Q(company__account__owner=user)
            ).distinct()
        
        # Filter by company
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        # Filter by status
        session_status = self.request.query_params.get('status')
        if session_status:
            queryset = queryset.filter(status=session_status)
        
        # Filter by phone number
        phone_number = self.request.query_params.get('phone_number')
        if phone_number:
            queryset = queryset.filter(phone_number__icontains=phone_number)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset.order_by('-last_activity_at')
    
    @action(detail=False, methods=['get'])
    def by_phone(self, request):
        """Get sessions by phone number."""
        phone_number = request.query_params.get('phone_number')
        company_id = request.query_params.get('company_id')
        
        if not phone_number:
            return Response(
                {'error': 'phone_number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(phone_number=phone_number)
        
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_notification(self, request, pk=None):
        """Manually send a notification to a session."""
        session = self.get_object()
        event_type = request.data.get('event_type')
        
        if not event_type:
            return Response(
                {'error': 'event_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get additional context
        context = request.data.get('context', {})
        
        service = AutomationService()
        success = service._send_notification(
            session.company,
            session,
            event_type,
            context
        )
        
        if success:
            return Response({
                'success': True,
                'message': f'Notification {event_type} sent successfully'
            })
        else:
            return Response({
                'success': False,
                'message': 'Failed to send notification or already sent'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update session status."""
        session = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'error': 'status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_statuses = [s[0] for s in CustomerSession.SessionStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Valid options: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session.status = new_status
        session.save(update_fields=['status'])
        
        return Response(CustomerSessionSerializer(session).data)
