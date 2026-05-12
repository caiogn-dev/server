"""
Celery tasks do sistema de agentes.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="agents", ignore_result=True, max_retries=2)
def learn_from_conversations(self, agent_id: str, lookback_hours: int = 24):
    """
    Extrai padrões de atendimentos recentes e atualiza AgentKnowledgeEntry.
    Rodado periodicamente pelo Celery Beat (a cada 6h por padrão).
    """
    try:
        from apps.agents.models import Agent
        from apps.agents.learning import AgentLearningService

        agent = Agent.objects.get(id=agent_id, status="active")
        svc = AgentLearningService(agent)
        stats = svc.learn(lookback_hours=lookback_hours)
        logger.info("[LEARN TASK] Agente %s → %s", agent.name, stats)
        return stats
    except Exception as exc:
        logger.exception("[LEARN TASK] Falha para agent_id=%s: %s", agent_id, exc)
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, queue="agents", ignore_result=True)
def learn_all_active_agents(self, lookback_hours: int = 24):
    """
    Dispara learn_from_conversations para todos os agentes ativos.
    Chamado pelo Celery Beat a cada 6h.
    """
    from apps.agents.models import Agent

    active = Agent.objects.filter(status="active").values_list("id", flat=True)
    dispatched = 0
    for agent_id in active:
        learn_from_conversations.delay(str(agent_id), lookback_hours=lookback_hours)
        dispatched += 1

    logger.info("[LEARN TASK] Disparou aprendizado para %d agentes ativos", dispatched)
    return {"dispatched": dispatched}


@shared_task(bind=True, queue="agents", ignore_result=True)
def decay_stale_knowledge(self):
    """
    Reduz confiança de entradas de conhecimento não usadas há 30 dias.
    Rodado diariamente.
    """
    from apps.agents.models import Agent
    from apps.agents.learning import AgentLearningService

    total_decayed = 0
    for agent in Agent.objects.filter(status="active"):
        svc = AgentLearningService(agent)
        n = svc.decay_unused(days_inactive=30)
        total_decayed += n

    logger.info("[LEARN TASK] Decay aplicado a %d entradas obsoletas", total_decayed)
    return {"decayed": total_decayed}
