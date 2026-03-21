"""
Pipeline Health — Métricas e Auditoria do Sistema de Mensagens

Fornece:
1. PipelineMetrics  — coleta e agrega métricas estruturadas de cada etapa do pipeline
2. health_check()   — retorna diagnóstico completo do sistema (Celery, DB, Redis, pipeline)
3. get_pipeline_stats() — resumo das últimas N horas para dashboards / alertas

Uso típico em views de administração:
    from apps.automation.services.pipeline_health import health_check, get_pipeline_stats
    status = health_check()           # {'status': 'ok'|'degraded'|'down', 'checks': {...}}
    stats  = get_pipeline_stats(24)   # métricas das últimas 24 horas

As métricas são gravadas no Django cache (Redis) e no logger estruturado.
Nenhuma dependência extra além das já usadas pelo projeto.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── Chaves de cache ─────────────────────────────────────────────────────────
_CACHE_PREFIX = 'pipeline_health'
_STATS_TTL = 3600  # 1 hora


# ─── Dataclasses de métricas ─────────────────────────────────────────────────

@dataclass
class PipelineEvent:
    """Representa um evento de processamento de mensagem no pipeline."""

    message_id: str
    source: str                    # 'handler' | 'template' | 'llm' | 'fallback' | 'agent_fallback' | 'dropped'
    intent: str = 'unknown'
    duration_ms: float = 0.0
    store_id: Optional[str] = None
    account_id: Optional[str] = None
    timed_out: bool = False
    dropped: bool = False
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


def record_pipeline_event(event: PipelineEvent) -> None:
    """
    Registra um evento do pipeline no logger estruturado e no cache de estatísticas.

    Chamado automaticamente pelo webhook_service ao final de cada processamento.
    """
    extra = {
        'pipeline.source': event.source,
        'pipeline.intent': event.intent,
        'pipeline.duration_ms': event.duration_ms,
        'pipeline.store_id': event.store_id,
        'pipeline.timed_out': event.timed_out,
        'pipeline.dropped': event.dropped,
        'message_id': event.message_id,
    }

    if event.dropped:
        logger.error('[pipeline.health] MESSAGE DROPPED — sem resposta para message_id=%s', event.message_id, extra=extra)
    elif event.timed_out:
        logger.warning('[pipeline.health] Timeout em message_id=%s (%.0fms)', event.message_id, event.duration_ms, extra=extra)
    else:
        logger.info('[pipeline.health] source=%s intent=%s (%.0fms)', event.source, event.intent, event.duration_ms, extra=extra)

    # Persiste contadores no cache
    try:
        _increment_counter(f'{_CACHE_PREFIX}:source:{event.source}')
        _increment_counter(f'{_CACHE_PREFIX}:intent:{event.intent}')
        if event.dropped:
            _increment_counter(f'{_CACHE_PREFIX}:dropped')
        if event.timed_out:
            _increment_counter(f'{_CACHE_PREFIX}:timeouts')
        _increment_counter(f'{_CACHE_PREFIX}:total')
    except Exception as exc:
        logger.debug('[pipeline.health] Falha ao gravar contador no cache: %s', exc)


def _increment_counter(key: str, ttl: int = _STATS_TTL) -> None:
    """Incrementa contador no Django cache de forma segura."""
    from django.core.cache import cache
    try:
        if not cache.get(key):
            cache.set(key, 0, ttl)
        cache.incr(key)
    except Exception:
        pass


# ─── Health Check ─────────────────────────────────────────────────────────────

def health_check() -> Dict[str, Any]:
    """
    Retorna diagnóstico completo do sistema de automação.

    Verifica:
    - Banco de dados (leitura de CompanyProfile)
    - Cache / Redis (set + get)
    - Celery (ping ao broker)
    - Agentes LLM configurados (sem fazer chamada real)
    - Fila de mensagens agendadas pendentes
    - Sessões expiradas não limpas

    Retorna dict com:
        status:  'ok' | 'degraded' | 'down'
        checks:  {nome: {ok: bool, detail: str}}
        summary: string legível
    """
    checks: Dict[str, Dict[str, Any]] = {}

    # 1. Banco de dados
    checks['database'] = _check_database()

    # 2. Cache / Redis
    checks['cache'] = _check_cache()

    # 3. Celery broker
    checks['celery'] = _check_celery()

    # 4. Agentes LLM configurados
    checks['agents'] = _check_agents()

    # 5. Mensagens agendadas com atraso
    checks['scheduled_messages'] = _check_scheduled_backlog()

    # 6. Sessões antigas não limpas
    checks['sessions'] = _check_stale_sessions()

    # Determina status global
    failed = [k for k, v in checks.items() if not v.get('ok')]
    if not failed:
        status = 'ok'
        summary = 'Todos os sistemas operacionais'
    elif set(failed) <= {'agents', 'scheduled_messages', 'sessions'}:
        status = 'degraded'
        summary = f'Degradado: {", ".join(failed)}'
    else:
        status = 'down'
        summary = f'Crítico: {", ".join(failed)}'

    return {
        'status': status,
        'summary': summary,
        'checks': checks,
        'checked_at': timezone.now().isoformat(),
    }


def _check_database() -> Dict[str, Any]:
    try:
        from apps.automation.models import CompanyProfile
        count = CompanyProfile.objects.count()
        return {'ok': True, 'detail': f'{count} CompanyProfile(s) no banco'}
    except Exception as exc:
        return {'ok': False, 'detail': f'Erro de DB: {exc}'}


def _check_cache() -> Dict[str, Any]:
    try:
        from django.core.cache import cache
        _key = f'{_CACHE_PREFIX}:healthcheck'
        cache.set(_key, 'ok', 10)
        val = cache.get(_key)
        if val == 'ok':
            return {'ok': True, 'detail': 'Cache Redis respondendo'}
        return {'ok': False, 'detail': f'Cache retornou valor inesperado: {val!r}'}
    except Exception as exc:
        return {'ok': False, 'detail': f'Erro de cache: {exc}'}


def _check_celery() -> Dict[str, Any]:
    try:
        from celery import current_app
        inspector = current_app.control.inspect(timeout=3)
        active = inspector.active()
        if active is None:
            return {'ok': False, 'detail': 'Nenhum worker Celery respondeu em 3s'}
        worker_count = len(active)
        return {'ok': True, 'detail': f'{worker_count} worker(s) ativos'}
    except Exception as exc:
        return {'ok': False, 'detail': f'Celery indisponível: {exc}'}


def _check_agents() -> Dict[str, Any]:
    try:
        from apps.agents.models import Agent
        total = Agent.objects.count()
        active = Agent.objects.filter(is_active=True).count()
        if active == 0:
            return {'ok': False, 'detail': f'Nenhum agente ativo (total: {total})'}
        return {'ok': True, 'detail': f'{active}/{total} agente(s) ativo(s)'}
    except Exception as exc:
        return {'ok': False, 'detail': f'Erro ao verificar agentes: {exc}'}


def _check_scheduled_backlog() -> Dict[str, Any]:
    """Verifica mensagens agendadas em atraso (> 5 min passado da data de envio)."""
    try:
        from apps.automation.models import ScheduledMessage
        cutoff = timezone.now() - timedelta(minutes=5)
        overdue = ScheduledMessage.objects.filter(
            status=ScheduledMessage.Status.PENDING,
            scheduled_at__lt=cutoff,
            is_active=True,
        ).count()
        if overdue > 0:
            return {'ok': False, 'detail': f'{overdue} mensagem(ns) agendada(s) em atraso > 5min'}
        return {'ok': True, 'detail': 'Sem backlog de mensagens agendadas'}
    except Exception as exc:
        return {'ok': False, 'detail': f'Erro ao verificar backlog: {exc}'}


def _check_stale_sessions() -> Dict[str, Any]:
    """Verifica sessões ativas há mais de 24h sem atividade (deveriam ter expirado)."""
    try:
        from apps.automation.models import CustomerSession
        cutoff = timezone.now() - timedelta(hours=24)
        stale = CustomerSession.objects.filter(
            last_activity_at__lt=cutoff,
            status__in=[
                CustomerSession.SessionStatus.ACTIVE,
                CustomerSession.SessionStatus.CART_CREATED,
            ],
        ).count()
        if stale > 50:
            return {'ok': False, 'detail': f'{stale} sessões obsoletas (cleanup pendente)'}
        return {'ok': True, 'detail': f'{stale} sessão(ões) obsoleta(s) — dentro do limite'}
    except Exception as exc:
        return {'ok': False, 'detail': f'Erro ao verificar sessões: {exc}'}


# ─── Estatísticas do Pipeline ─────────────────────────────────────────────────

def get_pipeline_stats(hours: int = 24) -> Dict[str, Any]:
    """
    Retorna estatísticas do pipeline das últimas `hours` horas.

    Lê contadores do cache Redis acumulados por record_pipeline_event().
    Complementa com dados do banco para métricas que exigem maior precisão.

    Retorna:
        {
          'period_hours': 24,
          'total_messages': int,
          'by_source': {'handler': N, 'template': N, 'llm': N, 'fallback': N, ...},
          'by_intent': {'greeting': N, 'menu_request': N, ...},
          'dropped': int,
          'timeouts': int,
          'intent_log_summary': [...],  # últimas intenções do banco
        }
    """
    from django.core.cache import cache

    def _get(key: str) -> int:
        try:
            return int(cache.get(f'{_CACHE_PREFIX}:{key}') or 0)
        except Exception:
            return 0

    sources = ['handler', 'template', 'llm', 'fallback', 'agent_fallback', 'dropped', 'error']
    by_source = {s: _get(f'source:{s}') for s in sources}

    # Intents mais comuns do banco (mais preciso que cache)
    intent_summary: List[Dict] = []
    try:
        from apps.automation.models import IntentLog
        cutoff = timezone.now() - timedelta(hours=hours)
        from django.db.models import Count
        rows = (
            IntentLog.objects
            .filter(created_at__gte=cutoff)
            .values('intent_type')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )
        intent_summary = list(rows)
    except Exception as exc:
        logger.debug('[pipeline_health] IntentLog query failed: %s', exc)

    return {
        'period_hours': hours,
        'total_messages': _get('total'),
        'by_source': by_source,
        'dropped': _get('dropped'),
        'timeouts': _get('timeouts'),
        'intent_log_summary': intent_summary,
        'generated_at': timezone.now().isoformat(),
    }
