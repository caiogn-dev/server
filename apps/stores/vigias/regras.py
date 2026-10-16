"""As regras dos vigias. Cada uma olha os dados e devolve fatos — ou nada.

Regra decide, nunca a IA: é testável, sai de graça e responde "por que me
avisou?" com números (`Fato.dados`). Toda regra:

- recebe a loja e `agora` e só lê pedidos DAQUELA loja;
- conta dinheiro e unidades pela regra única de receita
  (`metrics.pedidos_de_receita` / `itens_de_receita`): pago, não cancelado,
  não teste — o mesmo número do painel;
- exige amostra mínima antes de falar em variação. Com 10–17 pedidos por dia,
  percentual de base pequena é ruído (o "+404%" do resumo de agosto);
- compara por DIA ABERTO, não por semana: semana com feriado não é queda.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone
from django.utils.text import slugify

from apps.stores.metrics.definicoes import STATUS_SEM_RECEITA, _q_pedido_de_teste, itens_de_receita, pedidos_de_receita

DIAS_CURTOS = ('seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom')
DIAS_PLURAL = ('segundas', 'terças', 'quartas', 'quintas', 'sextas', 'sábados', 'domingos')


@dataclass
class Fato:
    tipo: str
    chave: str
    grupo: str
    titulo: str
    texto: str
    prioridade: int = 5
    #: Dias mínimos entre dois avisos do mesmo `grupo`.
    intervalo_dias: int = 0
    dados: dict = field(default_factory=dict)


# ── utilidades ────────────────────────────────────────────────────────────

def _local(agora: datetime) -> datetime:
    return timezone.localtime(agora) if timezone.is_aware(agora) else agora


def _data_da_receita(paid_at, created_at) -> date:
    return timezone.localtime(paid_at or created_at).date()


def dia_curto(d: date) -> str:
    return f'{DIAS_CURTOS[d.weekday()]} {d:%d/%m}'


def brl(valor) -> str:
    texto = f'{Decimal(valor):,.2f}'
    return 'R$ ' + texto.replace(',', '_').replace('.', ',').replace('_', '.')


def _semana_iso(d: date) -> str:
    ano, semana, _ = d.isocalendar()
    return f'{ano}-W{semana:02d}'


def _plural(n: int, singular: str, plural: str) -> str:
    return f'{n} {singular if n == 1 else plural}'


def _por_dia(loja, inicio: date, fim: date) -> dict:
    """{data: {'pedidos': n, 'receita': Decimal}} só dos dias com venda."""
    dias: dict = defaultdict(lambda: {'pedidos': 0, 'receita': Decimal('0')})
    for p in pedidos_de_receita(loja, inicio, fim).values('paid_at', 'created_at', 'total', 'delivery_fee'):
        d = _data_da_receita(p['paid_at'], p['created_at'])
        dias[d]['pedidos'] += 1
        dias[d]['receita'] += (p['total'] or 0) - (p['delivery_fee'] or 0)
    return dict(dias)


def _itens(loja, inicio: date, fim: date) -> list:
    """[(data, produto, qtd, preço unitário, custo unitário|None)]"""
    linhas = itens_de_receita(loja, inicio, fim).values(
        'order__paid_at', 'order__created_at', 'product_name', 'quantity', 'unit_price', 'unit_cost',
    )
    return [
        (_data_da_receita(i['order__paid_at'], i['order__created_at']), i['product_name'].strip(),
         i['quantity'] or 0, i['unit_price'] or Decimal('0'), i['unit_cost'])
        for i in linhas if (i['product_name'] or '').strip()
    ]


# ── 1. Resumo da manhã ────────────────────────────────────────────────────

def resumo_da_manha(loja, agora: datetime) -> list[Fato]:
    """O último dia de venda (até 3 dias atrás) contra o mesmo dia da semana.

    Segunda de manhã resume a sexta: o fim de semana fechado não é notícia.
    """
    hoje = _local(agora).date()
    por_dia = _por_dia(loja, hoje - timedelta(days=31), hoje - timedelta(days=1))
    dia = next((hoje - timedelta(days=k) for k in (1, 2, 3)
                if por_dia.get(hoje - timedelta(days=k), {}).get('pedidos')), None)
    if dia is None:
        return []

    n = por_dia[dia]['pedidos']
    receita = por_dia[dia]['receita']
    base = [por_dia[d]['pedidos'] for d in (dia - timedelta(days=7 * k) for k in range(1, 5)) if d in por_dia]

    rotulo = 'Ontem' if dia == hoje - timedelta(days=1) else dia_curto(dia).capitalize()
    partes = [f'{rotulo}: {_plural(n, "pedido", "pedidos")}, {brl(receita)}']
    variacao = None
    if len(base) >= 2:
        media = statistics.mean(base)
        variacao = round((n - media) / media * 100)
        plural = DIAS_PLURAL[dia.weekday()]
        if abs(variacao) < 10:
            partes[0] += f' — normal para as {plural}' if dia.weekday() < 5 else f' — normal para os {plural}'
        else:
            lado = 'acima' if variacao > 0 else 'abaixo'
            partes[0] += f' — {abs(variacao)}% {lado} da média das últimas {len(base)} {plural}'

    unidades: dict = defaultdict(int)
    for d, produto, qtd, _, _ in _itens(loja, dia, dia):
        unidades[produto] += qtd
    top = sorted(unidades.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
    if top:
        partes.append(('Mais vendido: ' if len(top) == 1 else 'Mais vendidos: ')
                      + ', '.join(f'{p} ({q})' for p, q in top))

    return [Fato(
        tipo='resumo', chave=f'resumo:{dia.isoformat()}', grupo='resumo',
        titulo=f'Resumo de {dia_curto(dia)}', texto='. '.join(partes) + '.', prioridade=10,
        dados={'dia': dia.isoformat(), 'pedidos': n, 'receita': str(receita),
               'base_dias': len(base), 'base_media': round(statistics.mean(base), 1) if base else None,
               'variacao_pct': variacao, 'mais_vendidos': [{'produto': p, 'qtd': q} for p, q in top]},
    )]


# ── 2. Sabor em queda ─────────────────────────────────────────────────────

#: Abaixo de 70% do esperado (queda > 30%) vira aviso.
QUEDA_MINIMA = 0.30


def sabor_em_queda(loja, agora: datetime) -> list[Fato]:
    """Últimos 7 dias contra as 4 semanas antes, normalizado por dia aberto."""
    hoje = _local(agora).date()
    fim = hoje - timedelta(days=1)
    ini_atual, fim_base, ini_base = fim - timedelta(days=6), fim - timedelta(days=7), fim - timedelta(days=34)

    por_dia = _por_dia(loja, ini_base, fim)
    abertos_atual = [d for d in por_dia if d >= ini_atual]
    abertos_base = [d for d in por_dia if d <= fim_base]
    if len(abertos_atual) < 3 or len(abertos_base) < 8:
        return []

    atual: dict = defaultdict(int)
    base: dict = defaultdict(int)
    for d, produto, qtd, _, _ in _itens(loja, ini_base, fim):
        (atual if d >= ini_atual else base)[produto] += qtd

    quedas = []
    for produto, total_base in base.items():
        if total_base < 8:
            continue
        esperado = total_base / len(abertos_base) * len(abertos_atual)
        vendido = atual.get(produto, 0)
        if esperado < 3 or vendido >= (1 - QUEDA_MINIMA) * esperado:
            continue
        quedas.append((esperado - vendido, produto, vendido, esperado))

    fatos = []
    for _, produto, vendido, esperado in sorted(quedas, reverse=True)[:2]:
        pct = round((1 - vendido / esperado) * 100)
        slug = slugify(produto) or 'produto'
        dias = len(abertos_atual)
        if vendido == 0:
            texto = f'{produto}: nenhuma venda nos últimos {dias} dias abertos; o normal seria ~{round(esperado)}.'
        else:
            texto = (f'{produto}: {_plural(vendido, "vendida", "vendidas")} nos últimos {dias} dias abertos; '
                     f'o normal seria ~{round(esperado)} (−{pct}%).')
        fatos.append(Fato(
            tipo='sabor_em_queda', chave=f'sabor_em_queda:{slug}:{_semana_iso(hoje)}',
            grupo=f'sabor_em_queda:{slug}', titulo=f'{produto} em queda', texto=texto,
            prioridade=7, intervalo_dias=14,
            dados={'produto': produto, 'vendido': vendido, 'esperado': round(esperado, 1),
                   'queda_pct': pct, 'dias_abertos': dias, 'dias_base': len(abertos_base)},
        ))
    return fatos


# ── 3. Cliente fiel sumiu ─────────────────────────────────────────────────

def fiel_sumiu(loja, agora: datetime) -> list[Fato]:
    """Quem pedia com ritmo (3+ pedidos) e passou do dobro do próprio intervalo.

    O intervalo é de CADA cliente: quem pede toda semana e some há 20 dias é
    notícia; quem pede uma vez por mês, não. Acima de 60 dias já não é alerta,
    é cliente perdido — outra conversa.
    """
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.stores.models import VigiaAviso

    agora = _local(agora)
    hoje = agora.date()
    pessoas: dict = defaultdict(lambda: {'dias': set(), 'nome': '', 'telefone': '', 'ultimo': None})
    for p in pedidos_de_receita(loja, hoje - timedelta(days=180), hoje).values(
            'customer_phone', 'customer_name', 'paid_at', 'created_at').order_by('created_at'):
        chave = chave_do_telefone(p['customer_phone'])
        if not chave:
            continue
        d = _data_da_receita(p['paid_at'], p['created_at'])
        pessoa = pessoas[chave]
        pessoa['dias'].add(d)
        if pessoa['ultimo'] is None or d >= pessoa['ultimo']:
            pessoa['ultimo'] = d
            pessoa['nome'] = (p['customer_name'] or '').strip() or pessoa['nome']
            pessoa['telefone'] = p['customer_phone']

    ja_avisados = set()
    for dados in VigiaAviso.objects.filter(
            store=loja, tipo='fiel_sumiu', criado_em__gte=agora - timedelta(days=30)).values_list('dados', flat=True):
        ja_avisados.update(c.get('chave') for c in (dados or {}).get('clientes_todos', []))

    sumidos = []
    for chave, pessoa in pessoas.items():
        dias = sorted(pessoa['dias'])
        if len(dias) < 3 or chave in ja_avisados:
            continue
        intervalo = statistics.median((b - a).days for a, b in zip(dias, dias[1:]))
        sem_pedir = (hoje - pessoa['ultimo']).days
        if sem_pedir > max(2 * intervalo, 10) and sem_pedir <= 60:
            sumidos.append({'chave': chave, 'nome': pessoa['nome'] or 'Cliente', 'telefone': pessoa['telefone'],
                            'intervalo': round(intervalo), 'sem_pedir': sem_pedir, 'pedidos': len(dias)})
    if not sumidos:
        return []

    sumidos.sort(key=lambda c: (-c['pedidos'], -c['sem_pedir']))
    mostrados = sumidos[:3]
    lista = ', '.join(f'{c["nome"]} (pedia a cada {c["intervalo"]} dias, há {c["sem_pedir"]} sem pedir)'
                      for c in mostrados)
    resto = f' +{len(sumidos) - 3}' if len(sumidos) > 3 else ''
    total = len(sumidos)
    return [Fato(
        tipo='fiel_sumiu', chave=f'fiel_sumiu:{_semana_iso(hoje)}', grupo='fiel_sumiu',
        titulo=_plural(total, 'cliente frequente sumiu', 'clientes frequentes sumiram'),
        texto=f'{_plural(total, "cliente que pedia com frequência sumiu", "clientes que pediam com frequência sumiram")}: {lista}{resto}.',
        prioridade=6, intervalo_dias=6,
        dados={'total': total, 'clientes': mostrados, 'clientes_todos': sumidos},
    )]


# ── 4. Custo e margem ─────────────────────────────────────────────────────

def _semana_de_itens(loja, hoje: date) -> list:
    return _itens(loja, hoje - timedelta(days=7), hoje - timedelta(days=1))


def sem_custo(loja, agora: datetime) -> list[Fato]:
    """Sabores vendidos sem custo cadastrado: o lucro deles fica fora da conta."""
    hoje = _local(agora).date()
    receita_total = Decimal('0')
    sem: dict = defaultdict(Decimal)
    for _, produto, qtd, preco, custo in _semana_de_itens(loja, hoje):
        receita_total += preco * qtd
        if custo is None:
            sem[produto] += preco * qtd
    if not sem or not receita_total:
        return []
    fatia = sum(sem.values()) / receita_total
    if fatia < Decimal('0.05'):
        return []
    produtos = [p for p, _ in sorted(sem.items(), key=lambda kv: -kv[1])]
    pct = round(fatia * 100)
    nomes = ', '.join(produtos[:4]) + (f' +{len(produtos) - 4}' if len(produtos) > 4 else '')
    return [Fato(
        tipo='sem_custo', chave=f'sem_custo:{_semana_iso(hoje)}', grupo='sem_custo',
        titulo=_plural(len(produtos), 'sabor sem custo', 'sabores sem custo'),
        texto=(f'{_plural(len(produtos), "item vendido", "itens vendidos")} na semana sem custo cadastrado '
               f'({pct}% da receita): {nomes}. Sem o custo, o lucro deles fica fora da conta.'),
        prioridade=3, intervalo_dias=28,
        dados={'produtos': produtos, 'fatia_pct': pct},
    )]


#: Margem (preço − custo) / preço abaixo disso, com volume, vira aviso.
MARGEM_MINIMA = Decimal('0.30')


def margem_baixa(loja, agora: datetime) -> list[Fato]:
    hoje = _local(agora).date()
    soma: dict = defaultdict(lambda: [0, Decimal('0'), Decimal('0')])  # qtd, receita, custo
    for _, produto, qtd, preco, custo in _semana_de_itens(loja, hoje):
        if custo is None:
            continue
        s = soma[produto]
        s[0] += qtd
        s[1] += preco * qtd
        s[2] += custo * qtd
    baixas = []
    for produto, (qtd, receita, custo) in soma.items():
        if qtd < 5 or not receita:
            continue
        margem = (receita - custo) / receita
        if margem < MARGEM_MINIMA:
            baixas.append((margem, produto, qtd, receita / qtd, custo / qtd))

    fatos = []
    for margem, produto, qtd, preco, custo in sorted(baixas)[:2]:
        slug = slugify(produto) or 'produto'
        pct = round(margem * 100)
        fatos.append(Fato(
            tipo='margem_baixa', chave=f'margem_baixa:{slug}:{_semana_iso(hoje)}', grupo=f'margem_baixa:{slug}',
            titulo=f'Margem baixa: {produto}',
            texto=f'{produto}: margem de {pct}% na semana (custo {brl(custo)} para preço médio {brl(preco)}).',
            prioridade=4, intervalo_dias=28,
            dados={'produto': produto, 'margem_pct': pct, 'qtd': qtd,
                   'preco_medio': str(round(preco, 2)), 'custo_medio': str(round(custo, 2))},
        ))
    return fatos


# ── 5. Nenhum pedido hoje (alerta) ────────────────────────────────────────

#: Depois disso o almoço já passou: avisar não muda mais nada.
HORA_LIMITE_DO_ALERTA = time(15, 0)


def _pedidos_ate(loja, dia: date, hora: time) -> int:
    from apps.stores.models import StoreOrder

    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(dia, time(0, 0)), tz)
    fim = timezone.make_aware(datetime.combine(dia, hora), tz)
    return (StoreOrder.objects.filter(store=loja, created_at__gte=inicio, created_at__lt=fim)
            .exclude(status__in=STATUS_SEM_RECEITA).exclude(_q_pedido_de_teste()).count())


def _teve_pedido(loja, dia: date) -> bool:
    return _pedidos_ate(loja, dia, time(23, 59, 59)) > 0


def sem_pedido_hoje(loja, agora: datetime, hora_alerta: time = time(12, 30)) -> list[Fato]:
    """Hoje sem nenhum pedido até a hora do alerta, num dia que costuma vender.

    Conta pedido operacional (inclusive PIX ainda pendente): o que importa é
    se cliente está conseguindo pedir, não se já pagou.
    """
    agora = _local(agora)
    hoje, hora = agora.date(), agora.time()
    if hora < hora_alerta or hora >= HORA_LIMITE_DO_ALERTA:
        return []
    if _pedidos_ate(loja, hoje, hora) > 0:
        return []

    mesmos_dias = [hoje - timedelta(days=7 * k) for k in range(1, 5)]
    base = [_pedidos_ate(loja, d, hora) for d in mesmos_dias if _teve_pedido(loja, d)]
    if len(base) < 2:
        return []
    normal = statistics.median(base)
    if normal < 3:
        return []
    plural = DIAS_PLURAL[hoje.weekday()]
    return [Fato(
        tipo='sem_pedido', chave=f'sem_pedido:{hoje.isoformat()}', grupo='sem_pedido',
        titulo=f'Nenhum pedido até {hora:%H:%M}',
        texto=(f'Até {hora:%H:%M} nenhum pedido hoje. Nas últimas {len(base)} {plural}, a essa hora já eram '
               f'{round(normal)} em média. Vale conferir se a loja está aberta no cardápio e o WhatsApp respondendo.'),
        prioridade=9,
        dados={'hora': f'{hora:%H:%M}', 'normal': normal, 'base': base},
    )]


#: Ordem = prioridade de exibição quando empatam.
REGRAS_DA_MANHA = (
    ('resumo', resumo_da_manha),
    ('sabor_em_queda', sabor_em_queda),
    ('fiel_sumiu', fiel_sumiu),
    ('margem_baixa', margem_baixa),
    ('sem_custo', sem_custo),
)
