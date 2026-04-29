"""
API views for print agents and print jobs.
"""
from __future__ import annotations

import logging

from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import StorePrintAgent, StorePrintJob
from apps.stores.services.print_service import (
    claim_next_print_job,
    complete_print_job,
    fail_print_job,
)
from ..serializers import (
    StorePrintAgentSerializer,
    StorePrintAgentCreateSerializer,
    StorePrintJobSerializer,
)
from .base import IsStoreOwnerOrStaff, filter_by_store

logger = logging.getLogger(__name__)


def _get_agent_from_request(request) -> StorePrintAgent | None:
    raw_key = request.headers.get('X-Print-Agent-Key') or request.META.get('HTTP_X_PRINT_AGENT_KEY', '')
    if not raw_key or '.' not in raw_key:
        return None

    prefix, _secret = raw_key.split('.', 1)
    agent = (
        StorePrintAgent.objects
        .select_related('store')
        .filter(api_key_prefix=prefix, is_active=True, status=StorePrintAgent.AgentStatus.ACTIVE)
        .first()
    )
    if not agent or not agent.verify_api_key(raw_key):
        return None
    return agent


class StorePrintAgentViewSet(viewsets.ModelViewSet):
    """Manage local print agents bound to a store."""

    queryset = StorePrintAgent.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def get_queryset(self):
        queryset = StorePrintAgent.objects.select_related('store').order_by('name')
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        if store_param:
            queryset, _ = filter_by_store(queryset, store_param)
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(Q(store__owner=self.request.user) | Q(store__staff=self.request.user)).distinct()

    def get_serializer_class(self):
        if self.action == 'create':
            return StorePrintAgentCreateSerializer
        return StorePrintAgentSerializer

    @action(detail=True, methods=['post'], url_path='rotate-key')
    def rotate_key(self, request, pk=None):
        agent = self.get_object()
        raw_key = agent.rotate_api_key()
        serializer = StorePrintAgentSerializer(agent)
        data = serializer.data
        data['api_key'] = raw_key
        return Response(data)


class StorePrintJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Read print jobs and allow manual retries."""

    queryset = StorePrintJob.objects.all()
    serializer_class = StorePrintJobSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def get_queryset(self):
        queryset = StorePrintJob.objects.select_related('store', 'order', 'claimed_by').order_by('-created_at')
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        if store_param:
            queryset, _ = filter_by_store(queryset, store_param)
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(Q(store__owner=self.request.user) | Q(store__staff=self.request.user)).distinct()

    @action(detail=True, methods=['post'], url_path='requeue')
    def requeue(self, request, pk=None):
        job = self.get_object()
        job.status = StorePrintJob.JobStatus.PENDING
        job.available_at = job.created_at
        job.last_error = ''
        job.save(update_fields=['status', 'available_at', 'last_error', 'updated_at'])
        return Response(StorePrintJobSerializer(job).data)


class PrintAgentHeartbeatView(APIView):
    """Record liveness data from an installed print agent."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request):
        agent = _get_agent_from_request(request)
        if not agent:
            return Response({'detail': 'Invalid print agent key'}, status=status.HTTP_401_UNAUTHORIZED)

        agent.mark_seen(
            ip_address=request.META.get('REMOTE_ADDR', ''),
            app_version=str(request.data.get('app_version') or ''),
            host_name=str(request.data.get('host_name') or ''),
        )
        return Response({'ok': True, 'agent_id': str(agent.id), 'store_id': str(agent.store_id)})


class PrintAgentClaimNextJobView(APIView):
    """Claim the next pending print job for this agent/station."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request):
        agent = _get_agent_from_request(request)
        if not agent:
            return Response({'detail': 'Invalid print agent key'}, status=status.HTTP_401_UNAUTHORIZED)

        agent.mark_seen(
            ip_address=request.META.get('REMOTE_ADDR', ''),
            app_version=str(request.data.get('app_version') or ''),
            host_name=str(request.data.get('host_name') or ''),
        )
        job = claim_next_print_job(agent)
        if not job:
            return Response({'job': None}, status=status.HTTP_200_OK)
        return Response({'job': StorePrintJobSerializer(job).data}, status=status.HTTP_200_OK)


class PrintAgentCompleteJobView(APIView):
    """Mark a claimed job as printed."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request, job_id):
        agent = _get_agent_from_request(request)
        if not agent:
            return Response({'detail': 'Invalid print agent key'}, status=status.HTTP_401_UNAUTHORIZED)

        job = (
            StorePrintJob.objects
            .select_related('store', 'claimed_by')
            .filter(id=job_id, store=agent.store)
            .first()
        )
        if not job:
            return Response({'detail': 'Print job not found'}, status=status.HTTP_404_NOT_FOUND)
        if job.claimed_by_id and job.claimed_by_id != agent.id:
            return Response({'detail': 'Print job claimed by another agent'}, status=status.HTTP_409_CONFLICT)

        complete_print_job(
            job,
            printer_name=str(request.data.get('printer_name') or ''),
            metadata=request.data.get('metadata') if isinstance(request.data.get('metadata'), dict) else None,
        )
        return Response({'ok': True, 'job': StorePrintJobSerializer(job).data})


class PrintAgentFailJobView(APIView):
    """Mark a claimed job as failed and optionally retry it."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request, job_id):
        agent = _get_agent_from_request(request)
        if not agent:
            return Response({'detail': 'Invalid print agent key'}, status=status.HTTP_401_UNAUTHORIZED)

        job = (
            StorePrintJob.objects
            .select_related('store', 'claimed_by')
            .filter(id=job_id, store=agent.store)
            .first()
        )
        if not job:
            return Response({'detail': 'Print job not found'}, status=status.HTTP_404_NOT_FOUND)
        if job.claimed_by_id and job.claimed_by_id != agent.id:
            return Response({'detail': 'Print job claimed by another agent'}, status=status.HTTP_409_CONFLICT)

        retryable = bool(request.data.get('retryable', True))
        retry_delay_seconds = int(request.data.get('retry_delay_seconds', 15))
        fail_print_job(
            job,
            error_message=str(request.data.get('error') or 'Unknown print error'),
            retryable=retryable,
            retry_delay_seconds=retry_delay_seconds,
        )
        return Response({'ok': True, 'job': StorePrintJobSerializer(job).data})
