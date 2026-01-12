"""
Langflow API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.whatsapp.models import WhatsAppAccount
from apps.conversations.models import Conversation
from ..models import LangflowFlow, LangflowSession, LangflowLog
from ..services import LangflowService
from .serializers import (
    LangflowFlowSerializer,
    LangflowFlowCreateSerializer,
    LangflowSessionSerializer,
    LangflowLogSerializer,
    ProcessMessageSerializer,
    ProcessMessageResponseSerializer,
    UpdateContextSerializer,
    AssignFlowSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List Langflow flows"),
    retrieve=extend_schema(summary="Get Langflow flow details"),
    create=extend_schema(summary="Create Langflow flow"),
    update=extend_schema(summary="Update Langflow flow"),
    partial_update=extend_schema(summary="Partial update Langflow flow"),
    destroy=extend_schema(summary="Delete Langflow flow"),
)
class LangflowFlowViewSet(viewsets.ModelViewSet):
    """ViewSet for Langflow Flow management."""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status']

    def get_queryset(self):
        return LangflowFlow.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action == 'create':
            return LangflowFlowCreateSerializer
        return LangflowFlowSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    @extend_schema(
        summary="Process message through flow",
        request=ProcessMessageSerializer,
        responses={200: ProcessMessageResponseSerializer}
    )
    @action(detail=False, methods=['post'])
    def process(self, request):
        """Process a message through a Langflow flow."""
        serializer = ProcessMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = LangflowService()
        
        conversation = None
        conversation_id = serializer.validated_data.get('conversation_id')
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id)
            except Conversation.DoesNotExist:
                pass
        
        try:
            result = service.process_message(
                flow_id=str(serializer.validated_data['flow_id']),
                message=serializer.validated_data['message'],
                context=serializer.validated_data.get('context', {}),
                session_id=serializer.validated_data.get('session_id'),
                conversation=conversation
            )
            
            return Response(ProcessMessageResponseSerializer(result).data)
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )

    @extend_schema(
        summary="Assign flow to accounts",
        request=AssignFlowSerializer,
        responses={200: LangflowFlowSerializer}
    )
    @action(detail=True, methods=['post'])
    def assign_accounts(self, request, pk=None):
        """Assign flow to WhatsApp accounts."""
        flow = self.get_object()
        serializer = AssignFlowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        account_ids = serializer.validated_data['account_ids']
        accounts = WhatsAppAccount.objects.filter(id__in=account_ids, is_active=True)
        
        flow.accounts.add(*accounts)
        
        return Response(LangflowFlowSerializer(flow).data)

    @extend_schema(
        summary="Remove flow from accounts",
        request=AssignFlowSerializer,
        responses={200: LangflowFlowSerializer}
    )
    @action(detail=True, methods=['post'])
    def remove_accounts(self, request, pk=None):
        """Remove flow from WhatsApp accounts."""
        flow = self.get_object()
        serializer = AssignFlowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        account_ids = serializer.validated_data['account_ids']
        accounts = WhatsAppAccount.objects.filter(id__in=account_ids)
        
        flow.accounts.remove(*accounts)
        
        return Response(LangflowFlowSerializer(flow).data)

    @extend_schema(
        summary="Get flow statistics",
        responses={200: dict}
    )
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get flow statistics."""
        service = LangflowService()
        stats = service.get_flow_stats(str(pk))
        return Response(stats)

    @extend_schema(
        summary="Get flow logs",
        responses={200: LangflowLogSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Get flow logs."""
        flow = self.get_object()
        logs = LangflowLog.objects.filter(flow=flow).order_by('-created_at')[:100]
        return Response(LangflowLogSerializer(logs, many=True).data)


@extend_schema_view(
    list=extend_schema(summary="List Langflow sessions"),
    retrieve=extend_schema(summary="Get Langflow session details"),
)
class LangflowSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Langflow Session management."""
    serializer_class = LangflowSessionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['flow', 'conversation']

    def get_queryset(self):
        return LangflowSession.objects.select_related('flow', 'conversation').all()

    @extend_schema(
        summary="Get session history",
        responses={200: list}
    )
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get session history."""
        session = self.get_object()
        return Response(session.history)

    @extend_schema(
        summary="Update session context",
        request=UpdateContextSerializer,
        responses={200: LangflowSessionSerializer}
    )
    @action(detail=True, methods=['post'])
    def update_context(self, request, pk=None):
        """Update session context."""
        session = self.get_object()
        serializer = UpdateContextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = LangflowService()
        session = service.update_session_context(
            session.session_id,
            serializer.validated_data['context']
        )
        
        return Response(LangflowSessionSerializer(session).data)

    @extend_schema(
        summary="Clear session history",
        responses={200: LangflowSessionSerializer}
    )
    @action(detail=True, methods=['post'])
    def clear_history(self, request, pk=None):
        """Clear session history."""
        session = self.get_object()
        
        service = LangflowService()
        session = service.clear_session_history(session.session_id)
        
        return Response(LangflowSessionSerializer(session).data)
