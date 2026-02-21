"""
Agent Flow API views - Flow Builder backend.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from apps.automation.models import AgentFlow, FlowSession, FlowExecutionLog
from apps.automation.api.serializers import (
    AgentFlowSerializer,
    CreateAgentFlowSerializer,
    UpdateAgentFlowSerializer,
    FlowSessionSerializer,
    FlowExecutionLogSerializer,
)
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class AgentFlowViewSet(viewsets.ModelViewSet):
    """ViewSet for AgentFlow CRUD operations - Flow Builder API."""
    
    queryset = AgentFlow.objects.select_related('store').filter(is_active=True)
    serializer_class = AgentFlowSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's stores
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(store__owner=user) | 
                Q(store__staff=user)
            ).distinct()
        
        # Filter by store
        store_id = self.request.query_params.get('store_id')
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        # Filter by store slug
        store_slug = self.request.query_params.get('store_slug')
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateAgentFlowSerializer
        elif self.action in ['update', 'partial_update']:
            return UpdateAgentFlowSerializer
        return AgentFlowSerializer
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate a flow."""
        try:
            flow = self.get_object()
            new_flow = AgentFlow.objects.create(
                name=f'{flow.name} (Cópia)',
                description=flow.description,
                store=flow.store,
                flow_json=flow.flow_json,
                is_active=True,
                is_default=False,
                version='1.0'
            )
            serializer = self.get_serializer(new_flow)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f'Error duplicating flow: {e}')
            return Response(
                {'error': 'Failed to duplicate flow'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set this flow as the default for the store."""
        try:
            flow = self.get_object()
            flow.set_as_default()
            return Response({'status': 'Flow set as default'})
        except Exception as e:
            logger.error(f'Error setting default flow: {e}')
            return Response(
                {'error': 'Failed to set default flow'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute/test a flow (for debugging)."""
        try:
            flow = self.get_object()
            node_id = request.data.get('node_id')
            context = request.data.get('context', {})
            
            # TODO: Implement flow execution via FlowExecutor
            # from apps.automation.services import FlowExecutor
            # executor = FlowExecutor(flow)
            # result = executor.execute_node(node_id, context)
            
            return Response({
                'status': 'Flow execution not yet implemented',
                'flow_id': str(flow.id),
                'node_id': node_id,
                'context': context
            })
        except Exception as e:
            logger.error(f'Error executing flow: {e}')
            return Response(
                {'error': 'Failed to execute flow'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FlowSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for FlowSession - read only for monitoring."""
    
    queryset = FlowSession.objects.select_related('conversation', 'flow')
    serializer_class = FlowSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security filter
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(flow__store__owner=user) | 
                Q(flow__store__staff=user)
            ).distinct()
        
        # Filter by flow
        flow_id = self.request.query_params.get('flow_id')
        if flow_id:
            queryset = queryset.filter(flow_id=flow_id)
        
        return queryset


class FlowExecutionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for FlowExecutionLog - read only for analytics."""
    
    queryset = FlowExecutionLog.objects.select_related('session', 'flow')
    serializer_class = FlowExecutionLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security filter
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(flow__store__owner=user) | 
                Q(flow__store__staff=user)
            ).distinct()
        
        # Filter by flow
        flow_id = self.request.query_params.get('flow_id')
        if flow_id:
            queryset = queryset.filter(flow_id=flow_id)
        
        return queryset
