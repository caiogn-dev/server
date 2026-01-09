"""
Audit API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.whatsapp.models import Message
from apps.orders.models import Order
from apps.conversations.models import Conversation
from apps.payments.models import Payment

from ..models import AuditLog, DataExportLog
from ..services import AuditService, ExportService
from .serializers import (
    AuditLogSerializer,
    DataExportLogSerializer,
    ExportRequestSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List audit logs"),
    retrieve=extend_schema(summary="Get audit log details"),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AuditLog operations."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['action', 'module', 'user_email']
    
    def get_queryset(self):
        return AuditLog.objects.all()
    
    @extend_schema(summary="Get my activity")
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_activity(self, request):
        """Get current user's activity."""
        service = AuditService()
        days = int(request.query_params.get('days', 30))
        limit = int(request.query_params.get('limit', 100))
        
        logs = service.get_user_activity(request.user, days=days, limit=limit)
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)
    
    @extend_schema(summary="Get object history")
    @action(detail=False, methods=['get'])
    def object_history(self, request):
        """Get audit history for a specific object."""
        object_type = request.query_params.get('type')
        object_id = request.query_params.get('id')
        
        if not object_type or not object_id:
            return Response(
                {'error': 'type and id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = AuditService()
        logs = service.get_logs(
            object_type=object_type,
            object_id=object_id,
            limit=50
        )
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="List exports"),
    retrieve=extend_schema(summary="Get export details"),
)
class ExportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Export operations."""
    serializer_class = DataExportLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['export_type', 'export_format', 'status']
    
    def get_queryset(self):
        return DataExportLog.objects.filter(user=self.request.user)
    
    @extend_schema(
        summary="Export data",
        request=ExportRequestSerializer,
    )
    @action(detail=False, methods=['post'])
    def export(self, request):
        """Export data to CSV or Excel."""
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        export_type = serializer.validated_data['export_type']
        export_format = serializer.validated_data['export_format']
        filters = serializer.validated_data.get('filters', {})
        
        export_service = ExportService()
        audit_service = AuditService()
        
        # Get queryset based on export type
        if export_type == 'messages':
            queryset = Message.objects.all()
            if filters.get('account'):
                queryset = queryset.filter(account_id=filters['account'])
            if filters.get('status'):
                queryset = queryset.filter(status=filters['status'])
            if filters.get('direction'):
                queryset = queryset.filter(direction=filters['direction'])
            response = export_service.export_messages(queryset, export_format, request.user)
            
        elif export_type == 'orders':
            queryset = Order.objects.filter(is_active=True)
            if filters.get('account'):
                queryset = queryset.filter(account_id=filters['account'])
            if filters.get('status'):
                queryset = queryset.filter(status=filters['status'])
            response = export_service.export_orders(queryset, export_format, request.user)
            
        elif export_type == 'conversations':
            queryset = Conversation.objects.filter(is_active=True)
            if filters.get('account'):
                queryset = queryset.filter(account_id=filters['account'])
            if filters.get('status'):
                queryset = queryset.filter(status=filters['status'])
            response = export_service.export_conversations(queryset, export_format, request.user)
            
        elif export_type == 'payments':
            queryset = Payment.objects.filter(is_active=True)
            if filters.get('status'):
                queryset = queryset.filter(status=filters['status'])
            response = export_service.export_payments(queryset, export_format, request.user)
        
        else:
            return Response(
                {'error': 'Invalid export type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Log the export
        audit_service.log_export(
            export_type=export_type,
            user=request.user,
            filters=filters,
            record_count=queryset.count(),
            request_info={
                'ip': request.META.get('REMOTE_ADDR', ''),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'path': request.path,
                'method': request.method,
            }
        )
        
        return response
