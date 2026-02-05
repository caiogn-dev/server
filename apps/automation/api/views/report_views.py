"""
Report API views.
"""
import logging
import os
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.http import FileResponse

from apps.automation.models import ReportSchedule, GeneratedReport
from apps.automation.api.serializers import (
    ReportScheduleSerializer,
    CreateReportScheduleSerializer,
    UpdateReportScheduleSerializer,
    GeneratedReportSerializer,
    GenerateReportSerializer,
)
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class ReportScheduleViewSet(viewsets.ModelViewSet):
    """ViewSet for ReportSchedule CRUD operations."""
    
    queryset = ReportSchedule.objects.select_related('account', 'company', 'company__store', 'created_by').filter(is_active=True)
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's accounts/stores or created by user
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(account__owner=user) |
                Q(company__store__owner=user) |
                Q(company__store__staff=user) |
                Q(created_by=user)
            ).distinct()
        
        # Filter by status
        schedule_status = self.request.query_params.get('status')
        if schedule_status:
            queryset = queryset.filter(status=schedule_status)
        
        # Filter by report type
        report_type = self.request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        # Filter by frequency
        frequency = self.request.query_params.get('frequency')
        if frequency:
            queryset = queryset.filter(frequency=frequency)
        
        return queryset.order_by('name')
    
    def create(self, request, *args, **kwargs):
        """Create a new report schedule."""
        serializer = CreateReportScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        account_id = data.pop('account_id', None)
        company_id = data.pop('company_id', None)
        
        schedule = ReportSchedule.objects.create(
            account_id=account_id,
            company_id=company_id,
            created_by=request.user,
            **data
        )
        
        # Calculate next run
        schedule.calculate_next_run()
        schedule.save()
        
        return Response(
            ReportScheduleSerializer(schedule).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a report schedule."""
        instance = self.get_object()
        serializer = UpdateReportScheduleSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        account_id = data.pop('account_id', None)
        company_id = data.pop('company_id', None)
        
        if account_id is not None:
            instance.account_id = account_id
        if company_id is not None:
            instance.company_id = company_id
        
        for key, value in data.items():
            setattr(instance, key, value)
        
        # Recalculate next run if schedule changed
        if any(k in data for k in ['frequency', 'day_of_week', 'day_of_month', 'hour', 'timezone']):
            instance.calculate_next_run()
        
        instance.save()
        return Response(ReportScheduleSerializer(instance).data)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete a report schedule."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """Run a report immediately."""
        schedule = self.get_object()
        
        from apps.automation.tasks import generate_report
        task = generate_report.delay(schedule_id=str(schedule.id))
        
        return Response({
            'success': True,
            'message': 'Report generation started',
            'task_id': task.id
        })
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a report schedule."""
        schedule = self.get_object()
        schedule.status = ReportSchedule.Status.PAUSED
        schedule.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Report schedule paused'
        })
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a paused report schedule."""
        schedule = self.get_object()
        schedule.status = ReportSchedule.Status.ACTIVE
        schedule.calculate_next_run()
        schedule.save()
        
        return Response({
            'success': True,
            'message': 'Report schedule resumed'
        })


class GeneratedReportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for GeneratedReport (read-only)."""
    
    queryset = GeneratedReport.objects.select_related('schedule', 'schedule__account', 'schedule__company', 'schedule__company__store', 'created_by')
    serializer_class = GeneratedReportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's accounts/stores or created by user
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(schedule__account__owner=user) |
                Q(schedule__company__store__owner=user) |
                Q(schedule__company__store__staff=user) |
                Q(created_by=user)
            ).distinct()
        
        # Filter by schedule
        schedule_id = self.request.query_params.get('schedule_id')
        if schedule_id:
            queryset = queryset.filter(schedule_id=schedule_id)
        
        # Filter by status
        report_status = self.request.query_params.get('status')
        if report_status:
            queryset = queryset.filter(status=report_status)
        
        # Filter by report type
        report_type = self.request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate a report on demand."""
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        from apps.automation.tasks import generate_report
        task = generate_report.delay(
            report_type=data.get('report_type', 'full'),
            period_start=data.get('period_start', '').isoformat() if data.get('period_start') else None,
            period_end=data.get('period_end', '').isoformat() if data.get('period_end') else None,
            account_id=str(data.get('account_id')) if data.get('account_id') else None,
            company_id=str(data.get('company_id')) if data.get('company_id') else None,
            recipients=data.get('recipients', []),
            export_format=data.get('export_format', 'xlsx'),
            user_id=request.user.id
        )
        
        return Response({
            'success': True,
            'message': 'Report generation started',
            'task_id': task.id
        })
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download a generated report."""
        report = self.get_object()
        
        if report.status != GeneratedReport.Status.COMPLETED:
            return Response(
                {'error': 'Report not ready for download'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not report.file_path or not os.path.exists(report.file_path):
            return Response(
                {'error': 'Report file not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return FileResponse(
            open(report.file_path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(report.file_path)
        )
    
    @action(detail=True, methods=['post'])
    def resend_email(self, request, pk=None):
        """Resend report email."""
        report = self.get_object()
        recipients = request.data.get('recipients', report.email_recipients)
        
        if not recipients:
            return Response(
                {'error': 'No recipients specified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from apps.automation.tasks.scheduled import _send_report_email
        _send_report_email(report, recipients)
        
        return Response({
            'success': True,
            'message': f'Report email sent to {recipients}'
        })
