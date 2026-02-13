"""
Automation Log API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from apps.automation.models import AutomationLog
from apps.automation.api.serializers import AutomationLogSerializer
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class AutomationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AutomationLog (read-only)."""
    
    queryset = AutomationLog.objects.select_related('company', 'company__store', 'company__account', 'session')
    serializer_class = AutomationLogSerializer
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
        
        # Filter by action type
        action_type = self.request.query_params.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        
        # Filter by error status
        is_error = self.request.query_params.get('is_error')
        if is_error is not None:
            queryset = queryset.filter(is_error=is_error.lower() == 'true')
        
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
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get log statistics."""
        company_id = request.query_params.get('company_id')
        
        queryset = self.get_queryset()
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        # Time ranges
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        
        # Stats by action type
        by_action = queryset.values('action_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Stats by day (last 7 days)
        by_day = []
        for i in range(7):
            day_start = today_start - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            count = queryset.filter(
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            by_day.append({
                'date': day_start.date().isoformat(),
                'count': count
            })
        
        # Error rate
        total = queryset.count()
        errors = queryset.filter(is_error=True).count()
        error_rate = (errors / total * 100) if total > 0 else 0
        
        return Response({
            'total': total,
            'today': queryset.filter(created_at__gte=today_start).count(),
            'this_week': queryset.filter(created_at__gte=week_start).count(),
            'errors': errors,
            'error_rate': round(error_rate, 2),
            'by_action_type': list(by_action),
            'by_day': by_day,
        })
