"""Insights de IA para o PAINEL do lojista (nunca no fluxo do cliente).

- Resumo diário: estatísticas de ontem + texto curto gerado por LLM.
- Análise de conversas: FAQs, reclamações e oportunidades das conversas
  recentes do WhatsApp da loja.

LLM indisponível NUNCA quebra o painel: cai no resumo template/estatísticas.
"""
import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings as dj_settings
from django.utils import timezone

logger = logging.getLogger(__name__)

INSIGHTS_MAX_MESSAGES = 300


def get_insights_llm():
    """LLM para análises internas — pseudo-agente pelo provider disponível no env."""
    from apps.agents.models import Agent
    from apps.agents.runtime.factory import create_llm

    candidates = [
        (Agent.AgentProvider.ANTHROPIC, 'ANTHROPIC_API_KEY', 'claude-haiku-4-5-20251001'),
        (Agent.AgentProvider.KIMI, 'KIMI_API_KEY',
         getattr(dj_settings, 'KIMI_MODEL_NAME', '') or 'moonshot-v1-8k'),
        (Agent.AgentProvider.OPENAI, 'OPENAI_API_KEY', 'gpt-4o-mini'),
    ]
    for provider, key_name, model in candidates:
        if getattr(dj_settings, key_name, ''):
            agent = Agent(
                name='painel-insights',
                provider=provider,
                model_name=model,
                temperature=0.3,
                max_tokens=1200,
                timeout=45,
            )
            return create_llm(agent)
    raise RuntimeError('Nenhum provider LLM configurado no ambiente')


def _llm_text(prompt: str) -> str:
    llm = get_insights_llm()
    result = llm.invoke(prompt)
    return getattr(result, 'content', str(result)).strip()


# ── Resumo diário ────────────────────────────────────────────────────────────

def compute_daily_stats(store, day=None) -> dict:
    """Números do dia (default: ontem) + comparação com o dia anterior."""
    from django.db.models import Count, Sum
    from apps.stores.models import StoreOrder, StoreOrderItem

    tz_now = timezone.localtime()
    day = day or (tz_now - timedelta(days=1)).date()
    prev_day = day - timedelta(days=1)

    def day_qs(d):
        return StoreOrder.objects.filter(store=store, created_at__date=d)

    def day_numbers(d):
        qs = day_qs(d).exclude(status__in=['cancelled', 'refunded', 'failed'])
        agg = qs.aggregate(count=Count('id'), revenue=Sum('total'))
        return agg['count'] or 0, float(agg['revenue'] or 0)

    count, revenue = day_numbers(day)
    prev_count, prev_revenue = day_numbers(prev_day)

    top_products = list(
        StoreOrderItem.objects.filter(
            order__store=store, order__created_at__date=day,
        ).exclude(order__status__in=['cancelled', 'refunded', 'failed'])
        .values('product_name')
        .annotate(qty=Sum('quantity'), total=Sum('subtotal'))
        .order_by('-qty')[:3]
    )

    hours = (
        day_qs(day).exclude(status__in=['cancelled', 'refunded', 'failed'])
        .values_list('created_at', flat=True)
    )
    hour_counts = {}
    for dt in hours:
        h = timezone.localtime(dt).hour
        hour_counts[h] = hour_counts.get(h, 0) + 1
    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

    cancelled = day_qs(day).filter(status__in=['cancelled', 'failed']).count()

    return {
        'date': day.isoformat(),
        'orders': count,
        'revenue': round(revenue, 2),
        'avg_ticket': round(revenue / count, 2) if count else 0,
        'orders_prev_day': prev_count,
        'revenue_prev_day': round(prev_revenue, 2),
        'top_products': [
            {'name': p['product_name'], 'qty': int(p['qty'] or 0), 'total': float(p['total'] or 0)}
            for p in top_products
        ],
        'peak_hour': peak_hour,
        'cancelled': cancelled,
    }


def _template_summary(store, stats: dict) -> str:
    parts = [
        f"📊 {stats['date']}: {stats['orders']} pedidos, R$ {stats['revenue']:.2f} de receita"
        f" (ticket médio R$ {stats['avg_ticket']:.2f})."
    ]
    if stats['orders_prev_day']:
        delta = stats['orders'] - stats['orders_prev_day']
        parts.append(f"{'+' if delta >= 0 else ''}{delta} pedidos vs dia anterior.")
    if stats['top_products']:
        top = stats['top_products'][0]
        parts.append(f"Mais vendido: {top['name']} ({top['qty']}x).")
    if stats['peak_hour'] is not None:
        parts.append(f"Pico às {stats['peak_hour']}h.")
    if stats['cancelled']:
        parts.append(f"⚠️ {stats['cancelled']} pedido(s) cancelado(s).")
    return ' '.join(parts)


def generate_daily_summary(store, day=None) -> dict:
    """Estatísticas + resumo em texto (LLM com fallback template)."""
    stats = compute_daily_stats(store, day)
    prompt = (
        "Você é um analista de negócios de um app de delivery. Escreva um resumo "
        "curto (3 a 5 frases, português do Brasil, tom direto e útil para o dono "
        f"do restaurante \"{store.name}\") sobre o desempenho de ontem. Destaque "
        "variações relevantes, o produto campeão, horário de pico e qualquer "
        "alerta. Não invente números.\n\nDados (JSON):\n"
        + json.dumps(stats, ensure_ascii=False)
    )
    try:
        summary = _llm_text(prompt)
        source = 'llm'
    except Exception as exc:
        logger.warning('[ai_insights] LLM indisponível para resumo diário: %s', exc)
        summary = _template_summary(store, stats)
        source = 'template'
    return {'stats': stats, 'summary': summary, 'source': source}


# ── Análise de conversas ─────────────────────────────────────────────────────

def collect_conversation_sample(store, days: int = 7) -> list:
    """Textos inbound recentes das conversas do WhatsApp da loja."""
    from apps.whatsapp.models import Message

    account = getattr(store, 'whatsapp_account', None)
    if not account:
        return []
    cutoff = timezone.now() - timedelta(days=days)
    msgs = (
        Message.objects.filter(
            conversation__account=account,
            direction='inbound',
            message_type='text',
            created_at__gte=cutoff,
        )
        .order_by('-created_at')[:INSIGHTS_MAX_MESSAGES]
        .values_list('content', flat=True)
    )
    texts = []
    for content in msgs:
        text = (content or {}).get('text') if isinstance(content, dict) else str(content or '')
        text = (text or '').strip()
        if text and len(text) > 1:
            texts.append(text[:300])
    return texts


def generate_conversation_insights(store, days: int = 7) -> dict:
    texts = collect_conversation_sample(store, days)
    base = {'days': days, 'message_count': len(texts)}
    if not texts:
        return {**base, 'insights': None, 'source': 'none',
                'summary': 'Sem mensagens de clientes no período.'}
    prompt = (
        "Você analisa conversas de clientes de um restaurante no WhatsApp "
        f"(\"{store.name}\"). Abaixo estão mensagens ENVIADAS POR CLIENTES nos "
        f"últimos {days} dias, uma por linha. Responda SOMENTE com JSON válido "
        "neste formato:\n"
        '{"faqs": ["pergunta frequente..."], "complaints": ["reclamação..."], '
        '"opportunities": ["oportunidade acionável..."], '
        '"sentiment": "positivo|neutro|negativo", "summary": "2-3 frases em pt-BR"}\n'
        "Máximo 5 itens por lista; listas vazias se não houver. Não invente.\n\n"
        + '\n'.join(texts)
    )
    try:
        raw = _llm_text(prompt)
        raw = raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        insights = json.loads(raw)
        return {**base, 'insights': insights,
                'summary': insights.get('summary', ''), 'source': 'llm'}
    except Exception as exc:
        logger.warning('[ai_insights] LLM indisponível para conversas: %s', exc)
        return {**base, 'insights': None, 'source': 'error',
                'summary': 'Análise de IA indisponível no momento — tente novamente em instantes.'}
