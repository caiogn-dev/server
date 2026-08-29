"""Insights de IA para o PAINEL do lojista (nunca no fluxo do cliente).

- Resumo diário: estatísticas de ontem + texto curto gerado por LLM.
- Análise de conversas: FAQs, reclamações e oportunidades das conversas
  recentes do WhatsApp da loja.

LLM indisponível NUNCA quebra o painel: cai no resumo template/estatísticas.
"""
import json
import re
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings as dj_settings
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Segundos que o painel espera pelo modelo antes de mostrar o template.
LLM_TIMEOUT_PAINEL = 18

INSIGHTS_MAX_MESSAGES = 300


# O catálogo vivo é do runtime dos agentes: painel e bot precisam concordar
# sobre qual modelo existe, e duas listas viram duas verdades na próxima morte.
from apps.agents.runtime.modelos import (  # noqa: E402
    FAMILIAS_COM_RACIOCINIO,
    MODELOS_APOSENTADOS,
    corpo_extra_do_modelo,
    modelo_vivo,
)

MODELO_INSIGHTS_PADRAO = 'nvidia/nemotron-3-nano-30b-a3b'


def modelo_de_insights() -> str:
    """O modelo do painel, ignorando env que aponte para lápide."""
    return modelo_vivo(
        getattr(dj_settings, 'NVIDIA_INSIGHTS_MODEL', ''),
        padrao=MODELO_INSIGHTS_PADRAO,
    )


def get_insights_llm():
    """LLM para análises internas — pseudo-agente pelo provider disponível no env."""
    from apps.agents.models import Agent
    from apps.agents.runtime.factory import create_llm

    nvidia_model = modelo_de_insights()
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
                # 45s era mais do que o dono espera olhando uma tela. O
                # template já está pronto e responde na hora; passar disso é
                # trocar uma resposta boa por uma tela parada.
                timeout=LLM_TIMEOUT_PAINEL,
                # O default do campo é a URL da Anthropic — zera p/ o factory
                # resolver a base_url correta do provider escolhido.
                base_url='',
            )
            return create_llm(agent)
    raise RuntimeError('Nenhum provider LLM configurado no ambiente')


def _llm_text(prompt: str) -> str:
    """Texto do modelo, já com os parâmetros que a família dele exige.

    O `extra_body` vai por `bind` e não no construtor porque o factory é
    compartilhado com o agente do WhatsApp: um parâmetro específico do painel
    não pode vazar para o fluxo do cliente.
    """
    llm = get_insights_llm()
    extra = corpo_extra_do_modelo(modelo_de_insights())
    if extra:
        llm = llm.bind(extra_body=extra)
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

    from apps.stores.metrics import pedidos_de_receita, itens_de_receita

    def day_qs(d):
        return StoreOrder.objects.filter(store=store, created_at__date=d)

    def day_numbers(d):
        # SSOT de receita. Antes excluía cancelado mas NÃO checava pagamento,
        # então pedido entregue com PIX pendente entrava como faturamento.
        qs = pedidos_de_receita(queryset=day_qs(d))
        agg = qs.aggregate(count=Count('id'), revenue=Sum('total'))
        return agg['count'] or 0, float(agg['revenue'] or 0)

    count, revenue = day_numbers(day)
    prev_count, prev_revenue = day_numbers(prev_day)

    top_products = list(
        itens_de_receita(loja=store, inicio=day, fim=day)
        .values('product_name')
        .annotate(qty=Sum('quantity'), total=Sum('subtotal'))
        .order_by('-qty')[:3]
    )

    hours = pedidos_de_receita(queryset=day_qs(day)).values_list('created_at', flat=True)
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
    from apps.stores.metrics import pedidos_de_receita, eixo_de_receita

    tz_now = timezone.localtime()
    day = day or (tz_now - timedelta(days=1)).date()
    inicio = day - timedelta(days=days - 1)

    # BAIXA EM LOTE: quando N pedidos compartilham o mesmo paid_at ao segundo, não
    # foi fluxo de caixa — foi alguém clicando "marcar como pago" numa fila. Na
    # Pastita, 5 pedidos de julho foram baixados em 03/08 16:51, um deles com 26
    # dias de atraso, empilhando R$ 1.489 num dia que não vendeu isso.
    # Nesses pedidos a data de referência volta a ser a da venda (created_at).
    # Agrupa por MINUTO, não por instante exato: uma baixa em lote leva alguns
    # segundos para percorrer a fila. Na Pastita os 6 pedidos ficaram entre
    # 16:51:41 e 16:51:53 — comparar timestamp exato nunca detectaria.
    lote_minimo = 3
    contagem = {}
    for ts in pedidos_de_receita(loja=store).exclude(paid_at=None).values_list('paid_at', flat=True):
        chave = ts.replace(second=0, microsecond=0)
        contagem[chave] = contagem.get(chave, 0) + 1
    minutos_de_lote = {m for m, n in contagem.items() if n >= lote_minimo}

    por_dia = {}
    for o in pedidos_de_receita(loja=store).only('created_at', 'paid_at', 'total'):
        quando = o.paid_at or o.created_at
        if o.paid_at and o.paid_at.replace(second=0, microsecond=0) in minutos_de_lote:
            quando = o.created_at
        d = timezone.localtime(quando).date()
        if not (inicio <= d <= day):
            continue
        n, v = por_dia.get(d, (0, 0.0))
        por_dia[d] = (n + 1, v + float(o.total or 0))

    # Dias sem venda contam como zero — senão a média mente para cima.
    diario = []
    for i in range(days):
        d = inicio + timedelta(days=i)
        o, r = por_dia.get(d, (0, 0.0))
        diario.append({'date': d.isoformat(), 'orders': o, 'revenue': round(r, 2),
                       'weekday': d.weekday()})

    receitas = [x['revenue'] for x in diario]
    media_dia = sum(receitas) / len(receitas) if receitas else 0.0
    dias_com_venda = sum(1 for x in diario if x['orders'] > 0)

    def _mediana(vals):
        """Robusta a outlier: um dia de R$ 3.000 não vira R$ 230/dia de projeção."""
        if not vals:
            return 0.0
        s = sorted(vals)
        meio = len(s) // 2
        return s[meio] if len(s) % 2 else (s[meio - 1] + s[meio]) / 2

    metade = len(receitas) // 2
    ant, rec = receitas[:metade], receitas[metade:]
    media_ant = sum(ant) / len(ant) if ant else 0.0
    media_rec = sum(rec) / len(rec) if rec else 0.0

    # A projeção usa a MEDIANA dos dias com venda da metade recente. A média era
    # sequestrada por um único pico (ou por uma baixa em lote que sobreviveu).
    rec_com_venda = [v for v in rec if v > 0]
    base_projecao = _mediana(rec_com_venda) * (len(rec_com_venda) / len(rec)) if rec else 0.0

    if media_ant > 0:
        tendencia_pct = round((media_rec - media_ant) / media_ant * 100, 1)
    else:
        tendencia_pct = 100.0 if media_rec > 0 else 0.0

    # Com pouquíssimo dia de venda o percentual é ruído: 2 dias em 28 produziam
    # "+404%". O painel usa esta flag para mostrar o número ou dizer "amostra pequena".
    tendencia_confiavel = dias_com_venda >= 8

    # Projeção do mês corrente: realizado + média diária recente x dias restantes.
    primeiro = day.replace(day=1)
    realizado = sum(x['revenue'] for x in diario if x['date'] >= primeiro.isoformat())
    import calendar
    dias_no_mes = calendar.monthrange(day.year, day.month)[1]
    restantes = dias_no_mes - day.day
    projecao_mes = realizado + (base_projecao * restantes)

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
        'trend_reliable': tendencia_confiavel,
        'days_with_sale': dias_com_venda,
        'month_realized': round(realizado, 2),
        'month_projection': round(projecao_mes, 2),
        'days_left_in_month': restantes,
        'best_weekday': NOMES[melhor] if melhor is not None else None,
        'worst_weekday': NOMES[pior] if pior is not None else None,
        'weekday_avg': {NOMES[k]: round(v, 2) for k, v in sorted(media_semana.items())},
        'days_without_sale': sum(1 for x in diario if x['orders'] == 0),
    }


# Tipos de bloco do resumo diário.
#
# Quatro, e só quatro: são as quatro perguntas que o dono faz ao abrir o painel
# de manhã — como foi ontem, para onde está indo, o que precisa de atenção, e o
# que eu faço hoje. Mais tipos que isso vira taxonomia sem uso, e o frontend
# precisa de um ícone e uma cor por tipo.
TIPOS_DE_BLOCO = ('resultado', 'tendencia', 'atencao', 'acao')


def _normalizar_bloco(bruto: dict) -> dict | None:
    """Um bloco do LLM vira bloco nosso, ou vira None.

    O modelo inventa rótulo — `insight_incrivel` já apareceu. Tipo fora do
    conjunto quebraria o ícone e a cor no frontend, então cai em 'resultado'
    (neutro) em vez de sumir: a informação continua valendo.

    Bloco sem texto é descartado: card com título e nada embaixo lê como falha
    nossa.
    """
    if not isinstance(bruto, dict):
        return None
    texto = str(bruto.get('texto') or '').strip()
    if not texto:
        return None
    tipo = str(bruto.get('tipo') or '').strip().lower()
    if tipo not in TIPOS_DE_BLOCO:
        tipo = 'resultado'
    return {
        'tipo': tipo,
        'titulo': str(bruto.get('titulo') or '').strip() or 'Resumo',
        'texto': texto,
    }


def _blocos_do_json(bruto: str) -> list:
    """Extrai os blocos da resposta do LLM.

    Modelo instruído a devolver JSON devolve ```json … ``` boa parte das vezes.
    Falhar nisso jogaria todo mundo no template sem motivo — a resposta estava
    certa, só embrulhada.
    """
    texto = (bruto or '').strip()
    if texto.startswith('```'):
        texto = re.sub(r'^```[a-zA-Z]*\s*', '', texto)
        texto = re.sub(r'\s*```$', '', texto)
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return []
    brutos = dados.get('blocos') if isinstance(dados, dict) else dados
    if not isinstance(brutos, list):
        return []
    return [b for b in (_normalizar_bloco(x) for x in brutos) if b]


def _template_blocos(store, stats: dict, forecast: dict = None) -> list:
    """Os MESMOS blocos, sem LLM.

    O provedor é externo e cai. Quando cair, a tela não pode mudar de forma —
    se o fallback devolvesse só texto, o card alternaria entre dois layouts sem
    ninguém entender por quê.
    """
    forecast = forecast or {}
    blocos = []

    resultado = (
        f"{stats['orders']} pedidos e R$ {stats['revenue']:.2f} de receita "
        f"(ticket médio R$ {stats['avg_ticket']:.2f})."
    )
    if stats.get('orders_prev_day'):
        delta = stats['orders'] - stats['orders_prev_day']
        resultado += f" {'+' if delta >= 0 else ''}{delta} pedidos contra o dia anterior."
    blocos.append({'tipo': 'resultado', 'titulo': 'Como foi ontem', 'texto': resultado})

    t = forecast.get('trend_pct')
    if t is not None:
        direcao = 'subindo' if t > 0 else ('estável' if t == 0 else 'caindo')
        texto = f"O movimento está {direcao} ({t:+.1f}% desde o início do período)."
        proj = forecast.get('month_projection')
        if proj:
            texto += (
                f" Projeção de fechamento do mês: R$ {proj:.2f}, com "
                f"R$ {forecast.get('month_realized', 0):.2f} já realizados."
            )
        blocos.append({'tipo': 'tendencia', 'titulo': 'Para onde está indo', 'texto': texto})

    atencao = []
    if stats.get('cancelled'):
        atencao.append(f"{stats['cancelled']} pedido(s) cancelado(s) ontem.")
    if forecast.get('days_without_sale'):
        atencao.append(f"{forecast['days_without_sale']} dia(s) sem venda nenhuma no período.")
    if atencao:
        blocos.append({'tipo': 'atencao', 'titulo': 'Precisa de atenção', 'texto': ' '.join(atencao)})

    acao = []
    if stats.get('top_products'):
        top = stats['top_products'][0]
        acao.append(f"{top['name']} foi o mais vendido ({top['qty']}x) — vale virar combo.")
    if stats.get('peak_hour') is not None:
        acao.append(f"O pico foi às {stats['peak_hour']}h; reforce a equipe nesse horário.")
    if forecast.get('worst_weekday'):
        acao.append(f"{forecast['worst_weekday']} é o dia mais fraco — bom alvo para promoção.")
    if acao:
        blocos.append({'tipo': 'acao', 'titulo': 'O que fazer hoje', 'texto': ' '.join(acao)})

    return blocos


def _texto_dos_blocos(blocos: list) -> str:
    """Versão em texto corrido, para quem só sabe ler string.

    WhatsApp e e-mail consomem `summary`. Trocar o contrato sem manter o campo
    quebraria os dois em silêncio.
    """
    return ' '.join(f"{b['titulo']}: {b['texto']}" for b in blocos)


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
        f"\"{store.name}\". Responda APENAS com JSON válido, sem texto antes ou "
        "depois, sem cercas de código.\n\n"
        "Formato:\n"
        '{"blocos":[{"tipo":"...","titulo":"...","texto":"..."}]}\n\n'
        "Gere de 3 a 4 blocos, nesta ordem, usando SÓ estes tipos:\n"
        "- resultado: como foi ontem, com os números.\n"
        "- tendencia: subindo ou caindo e quanto (trend_pct), e a projeção do "
        "mês (month_projection) contra o já realizado (month_realized).\n"
        "- atencao: só se houver cancelamento, dia sem venda ou projeção abaixo "
        "do mês passado. Se não houver, omita o bloco.\n"
        "- acao: UMA coisa concreta para hoje, tirada dos dados — o dia fraco "
        "(worst_weekday), o campeão que pode virar combo, o horário de pico que "
        "pede reforço.\n\n"
        "titulo: no máximo 4 palavras. texto: 1 a 2 frases, português do Brasil, "
        "tom de quem conversa com o dono, sem jargão.\n\n"
        "Regras: não invente número fora dos dados. Se a projeção for menor que "
        "o mês passado, diga sem suavizar. Se não houve venda, diga com "
        "franqueza. Nunca use 'insight', 'otimizar' ou 'alavancar'.\n\n"
        "Dados de ontem (JSON):\n" + json.dumps(stats, ensure_ascii=False) +
        "\n\nTendência e projeção (JSON):\n" + json.dumps(forecast, ensure_ascii=False)
    )

    blocos = []
    source = 'template'
    try:
        blocos = _blocos_do_json(_llm_text(prompt))
        if blocos:
            source = 'llm'
    except Exception as exc:
        logger.warning('[ai_insights] LLM indisponível para resumo diário: %s', exc)

    if not blocos:
        # JSON inválido, lista vazia ou todos os blocos sem texto: o template
        # tem o que dizer, e um card vazio leria como falha nossa.
        blocos = _template_blocos(store, stats, forecast)
        source = 'template'

    return {
        'stats': stats,
        'forecast': forecast,
        'blocos': blocos,
        # Mantido para WhatsApp e e-mail, que só sabem ler string. Sai DOS
        # blocos, não de uma segunda chamada ao modelo.
        'summary': _texto_dos_blocos(blocos),
        'source': source,
    }


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
