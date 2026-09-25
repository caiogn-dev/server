"""
API views for print agents and print jobs.
"""
from __future__ import annotations

import json
import logging
import time

from django.db.models import Q
from django.http import StreamingHttpResponse
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store, StorePrintAgent, StorePrintJob
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
from apps.core.permissions import accessible_store_ids

logger = logging.getLogger(__name__)


def _uuid_valido(valor) -> bool:
    import uuid as _uuid
    try:
        _uuid.UUID(str(valor))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _recusa(request, prefix: str, motivo: str) -> None:
    """Um 401 mudo não diz qual PC está com a chave errada. O prefixo é público
    (aparece no painel); o segredo nunca entra no log."""
    logger.warning(
        'print-agent recusado: prefixo=%s motivo=%s ip=%s host=%s path=%s',
        prefix or '-', motivo,
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', ''),
        str(getattr(request, 'data', {}).get('host_name', '') if hasattr(request, 'data') else ''),
        request.path,
    )


def _get_agent_from_request(request) -> StorePrintAgent | None:
    raw_key = request.headers.get('X-Print-Agent-Key') or request.META.get('HTTP_X_PRINT_AGENT_KEY', '')
    if not raw_key or '.' not in raw_key:
        _recusa(request, raw_key[:32], 'formato_invalido')
        return None

    prefix, _secret = raw_key.split('.', 1)
    agent = (
        StorePrintAgent.objects
        .select_related('store')
        .filter(api_key_prefix=prefix)
        .first()
    )
    if not agent:
        _recusa(request, prefix, 'prefixo_desconhecido')
        return None
    if not agent.is_active or agent.status != StorePrintAgent.AgentStatus.ACTIVE:
        _recusa(request, prefix, 'agente_inativo')
        return None
    if not agent.verify_api_key(raw_key):
        _recusa(request, prefix, 'segredo_errado')
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
        return queryset.filter(store_id__in=accessible_store_ids(self.request.user))

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
        return queryset.filter(store_id__in=accessible_store_ids(self.request.user))

    @action(detail=False, methods=['post'], url_path='etiquetas')
    def etiquetas(self, request):
        """Etiqueta (validade / nutricional / QR) para a Zebra de um agent.

        O painel manda os mesmos dados que usa na impressão pelo navegador;
        aqui viram ZPL e entram na fila apontados para o agent escolhido —
        nunca para "qualquer agent da loja", senão a etiqueta cai na Epson.
        """
        from apps.stores import billing
        from apps.stores.services.etiquetas_zpl import MODELOS, render_etiquetas

        dados = request.data if hasattr(request.data, 'get') else {}
        modelo = str(dados.get('modelo') or '')
        etiquetas = dados.get('etiquetas')
        if modelo not in MODELOS:
            return Response({'detail': f'modelo inválido: {modelo}'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(etiquetas, list) or not etiquetas:
            return Response({'detail': 'Nenhuma etiqueta para imprimir.'}, status=status.HTTP_400_BAD_REQUEST)

        store = Store.objects.filter(
            id__in=accessible_store_ids(request.user), pk=dados.get('store'),
        ).first() if _uuid_valido(dados.get('store')) else None
        if not store:
            return Response({'detail': 'Loja não encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        agent = StorePrintAgent.objects.filter(
            pk=dados.get('agent'), store=store, is_active=True,
            status=StorePrintAgent.AgentStatus.ACTIVE,
        ).first() if _uuid_valido(dados.get('agent')) else None
        if not agent:
            return Response({'detail': 'Escolha um programa de impressão desta loja.'}, status=status.HTTP_400_BAD_REQUEST)

        if modelo.startswith('nutricao') and not billing.loja_tem_adicional(store, 'etiqueta_anvisa'):
            from apps.nutrition.api.permissions import AdicionalNecessario
            raise AdicionalNecessario()

        zpl = render_etiquetas(modelo, etiquetas, dados.get('config') or {})
        job = StorePrintJob.objects.create(
            store=store,
            station=agent.station,
            template=StorePrintJob.Template.ETIQUETA_ZPL,
            source=StorePrintJob.Source.ETIQUETA,
            title=f'Etiquetas {modelo} ×{len(etiquetas)} → {agent.name}',
            payload={'zpl': zpl, 'modelo': modelo, 'quantidade': len(etiquetas)},
            target_agent=agent,
            max_attempts=agent.max_retries,
            metadata={'requested_by': str(request.user.id)},
        )
        return Response({'job': StorePrintJobSerializer(job).data}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='requeue')
    def requeue(self, request, pk=None):
        job = self.get_object()

        # Reimprimir cria um job NOVO (id/dedupe novos): o agent guarda os ids
        # já impressos e marcaria o mesmo id como "duplicata" sem imprimir.
        if job.order_id:
            from apps.stores.services.print_service import enqueue_order_print_job
            result = enqueue_order_print_job(
                job.order,
                station=job.station,
                template=job.template,
                source=StorePrintJob.Source.MANUAL_REPRINT,
                dedupe=False,
                requested_by=getattr(request.user, 'username', '') or '',
            )
            return Response(StorePrintJobSerializer(result.job).data)

        # Job sem pedido (ex.: teste): comportamento antigo
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

        # Impressoras detectadas no PC do agent (popula o dropdown do painel)
        printers = request.data.get('available_printers')
        if isinstance(printers, list):
            cleaned = [str(name)[:255] for name in printers if str(name).strip()][:50]
            if cleaned and cleaned != agent.available_printers:
                agent.available_printers = cleaned
                agent.save(update_fields=['available_printers', 'updated_at'])

        from apps.stores.services import vigia_de_impressao

        return Response({
            'ok': True,
            'agent_id': str(agent.id),
            'store_id': str(agent.store_id),
            # O agent obedece a impressora escolhida no painel
            'printer_name': agent.printer_name,
            # O agent avisa no log quando está velho; o painel mostra o selo.
            'versao_atual': vigia_de_impressao.VERSAO_ATUAL_DO_AGENT,
            'versao_desatualizada': vigia_de_impressao.versao_desatualizada(agent.app_version),
        })


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


class PrintAgentWatchJobsView(APIView):
    """Watch for new print jobs via Server-Sent Events (SSE)."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def get(self, request):
        agent = _get_agent_from_request(request)
        if not agent:
            return Response({'detail': 'Invalid print agent key'}, status=status.HTTP_401_UNAUTHORIZED)

        agent.mark_seen(
            ip_address=request.META.get('REMOTE_ADDR', ''),
            app_version=str(request.GET.get('app_version') or ''),
            host_name=str(request.GET.get('host_name') or ''),
        )

        def event_generator():
            last_job_id = None
            consecutive_empties = 0
            max_consecutive_empties = 60  # max 2 min of no jobs before timeout

            while consecutive_empties < max_consecutive_empties:
                try:
                    job = claim_next_print_job(agent)
                    if job:
                        consecutive_empties = 0
                        payload = StorePrintJobSerializer(job).data
                        event_data = json.dumps({'type': 'job', 'data': payload})
                        yield f"data: {event_data}\n\n"
                        last_job_id = job.id
                    else:
                        consecutive_empties += 1
                        yield f": heartbeat\n\n"
                    time.sleep(2)
                except Exception as e:
                    logger.error('SSE event_generator error: %s', e)
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Erro interno no servidor.'})}\n\n"
                    time.sleep(5)

        response = StreamingHttpResponse(
            event_generator(),
            content_type='text/event-stream',
            status=200,
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'
        return response
