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

    # NVIDIA NIM é o provider da casa. O NVIDIA_MODEL_NAME do .env pode estar
    # aposentado no catálogo (caso do llama-3.1-405b em 15/jul) — estes
    # insights usam um modelo próprio com default vivo.
    nvidia_model = (
        getattr(dj_settings, 'NVIDIA_INSIGHTS_MODEL', '')
        or 'meta/llama-3.1-70b-instruct'
    )
    candidates = [
        (Agent.AgentProvider.NVIDIA, 'NVIDIA_API_KEY', nvidia_model),
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
                # O default do campo é a URL da Anthropic — zera p/ o factory
                # resolver a base_url correta do provider escolhido.
                base_url='',
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

    from apps.stores.services.revenue import revenue_orders, revenue_items

    def day_qs(d):
        return StoreOrder.objects.filter(store=store, created_at__date=d)

    def day_numbers(d):
        # SSOT de receita. Antes excluía cancelado mas NÃO checava pagamento,
        # então pedido entregue com PIX pendente entrava como faturamento.
        qs = revenue_orders(queryset=day_qs(d))
        agg = qs.aggregate(count=Count('id'), revenue=Sum('total'))
        return agg['count'] or 0, float(agg['revenue'] or 0)

    count, revenue = day_numbers(day)
    prev_count, prev_revenue = day_numbers(prev_day)

    top_products = list(
        revenue_items(store=store, start=day, end=day)
        .values('product_name')
        .annotate(qty=Sum('quantity'), total=Sum('subtotal'))
        .order_by('-qty')[:3]
    )

    hours = revenue_orders(queryset=day_qs(day)).values_list('created_at', flat=True)
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


def compute_forecast(store, days: int = 28, day=None) -> dict:
    """Projeção do mês e tendência, a partir do histórico de receita real.

    Só descrever ontem não ajuda o dono a decidir nada. Isto responde três
    perguntas que ele tem de fato: quanto vou fechar o mês, estou subindo ou
    caindo, e qual é o meu melhor e pior dia da semana.

    Método deliberadamente simples e explicável (nada de modelo opaco num painel
    que precisa ser confiável): média diária das últimas `days` janelas, tendência
    comparando as duas metades do período, e projeção linear do mês corrente.
    """
    from django.db.models import Count, Sum
    from django.db.models.functions import TruncDate
    from apps.stores.services.revenue import revenue_orders, revenue_date_field

    tz_now = timezone.localtime()
    day = day or (tz_now - timedelta(days=1)).date()
    inicio = day - timedelta(days=days - 1)

    series = list(
        revenue_orders(store=store, start=inicio, end=day)
        .annotate(d=TruncDate(revenue_date_field()))
        .values('d')
        .annotate(orders=Count('id'), revenue=Sum('total'))
        .order_by('d')
    )
    por_dia = {r['d']: (r['orders'], float(r['revenue'] or 0)) for r in series}

    # Dias sem venda contam como zero — senão a média mente para cima.
    diario = []
    for i in range(days):
        d = inicio + timedelta(days=i)
        o, r = por_dia.get(d, (0, 0.0))
        diario.append({'date': d.isoformat(), 'orders': o, 'revenue': round(r, 2),
                       'weekday': d.weekday()})

    receitas = [x['revenue'] for x in diario]
    media_dia = sum(receitas) / len(receitas) if receitas else 0.0

    metade = len(receitas) // 2
    ant, rec = receitas[:metade], receitas[metade:]
    media_ant = sum(ant) / len(ant) if ant else 0.0
    media_rec = sum(rec) / len(rec) if rec else 0.0
    if media_ant > 0:
        tendencia_pct = round((media_rec - media_ant) / media_ant * 100, 1)
    else:
        tendencia_pct = 100.0 if media_rec > 0 else 0.0

    # Projeção do mês corrente: realizado + média diária recente x dias restantes.
    primeiro = day.replace(day=1)
    realizado = sum(x['revenue'] for x in diario if x['date'] >= primeiro.isoformat())
    import calendar
    dias_no_mes = calendar.monthrange(day.year, day.month)[1]
    restantes = dias_no_mes - day.day
    projecao_mes = realizado + (media_rec * restantes)

    # Melhor e pior dia da semana (0=segunda).
    por_semana = {}
    for x in diario:
        por_semana.setdefault(x['weekday'], []).append(x['revenue'])
    media_semana = {k: sum(v) / len(v) for k, v in por_semana.items() if v}
    NOMES = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
    melhor = max(media_semana, key=media_semana.get) if media_semana else None
    pior = min(media_semana, key=media_semana.get) if media_semana else None

    return {
        # Série diária completa: é o que o painel plota. Sem ela o front teria de
        # refazer a query só para desenhar a mesma coisa.
        'daily': diario,
        'window_days': days,
        'daily_avg_revenue': round(media_dia, 2),
        'recent_avg_revenue': round(media_rec, 2),
        'trend_pct': tendencia_pct,
        'month_realized': round(realizado, 2),
        'month_projection': round(projecao_mes, 2),
        'days_left_in_month': restantes,
        'best_weekday': NOMES[melhor] if melhor is not None else None,
        'worst_weekday': NOMES[pior] if pior is not None else None,
        'weekday_avg': {NOMES[k]: round(v, 2) for k, v in sorted(media_semana.items())},
        'days_without_sale': sum(1 for x in diario if x['orders'] == 0),
    }


def _template_summary(store, stats: dict, forecast: dict = None) -> str:
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
    # Mesmo sem LLM o dono precisa da tendência e da projeção — é o que ele usa
    # para decidir. Sem isto o fallback só narrava ontem.
    if forecast:
        t = forecast.get('trend_pct')
        if t is not None:
            direcao = 'subindo' if t > 0 else ('estável' if t == 0 else 'caindo')
            parts.append(f"Tendência {direcao} ({t:+.1f}% vs início do período).")
        proj = forecast.get('month_projection')
        if proj:
            parts.append(
                f"Projeção do mês: R$ {proj:.2f} "
                f"(R$ {forecast.get('month_realized', 0):.2f} já realizados, "
                f"{forecast.get('days_left_in_month', 0)} dias restantes)."
            )
        if forecast.get('worst_weekday'):
            parts.append(f"Dia mais fraco: {forecast['worst_weekday']}.")
        if forecast.get('days_without_sale'):
            parts.append(f"{forecast['days_without_sale']} dia(s) sem venda no período.")
    return ' '.join(parts)


def generate_daily_summary(store, day=None) -> dict:
    """Estatísticas + resumo em texto (LLM com fallback template)."""
    stats = compute_daily_stats(store, day)
    try:
        forecast = compute_forecast(store, day=day)
    except Exception as exc:
        logger.warning('[ai_insights] falha no forecast: %s', exc)
        forecast = {}

    prompt = (
        "Você é o analista de negócios do dono do restaurante "
        f"\"{store.name}\". Escreva 4 a 6 frases em português do Brasil, tom "
        "direto, como quem conversa com o dono — sem jargão e sem bullet.\n\n"
        "Estrutura obrigatória, nesta ordem:\n"
        "1. Como foi ontem, em uma frase, com o número.\n"
        "2. A TENDÊNCIA: está subindo ou caindo, e quanto (use trend_pct).\n"
        "3. A PROJEÇÃO de fechamento do mês (month_projection) comparada ao que já "
        "foi realizado (month_realized).\n"
        "4. UMA ação concreta para hoje, derivada dos dados — o dia fraco da semana "
        "(worst_weekday), o produto campeão que pode virar combo, o horário de pico "
        "que pede reforço, ou os dias sem venda nenhuma.\n\n"
        "Regras: não invente número que não esteja nos dados. Se a projeção for "
        "menor que o realizado do mês passado, diga isso sem suavizar. Se não houve "
        "venda, diga com franqueza e sugira o que fazer. Nunca use as palavras "
        "'insight', 'otimizar' ou 'alavancar'.\n\n"
        "Dados de ontem (JSON):\n" + json.dumps(stats, ensure_ascii=False) +
        "\n\nTendência e projeção (JSON):\n" + json.dumps(forecast, ensure_ascii=False)
    )
    try:
        summary = _llm_text(prompt)
        source = 'llm'
    except Exception as exc:
        logger.warning('[ai_insights] LLM indisponível para resumo diário: %s', exc)
        summary = _template_summary(store, stats, forecast)
        source = 'template'
    return {'stats': stats, 'forecast': forecast, 'summary': summary, 'source': source}


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
