"""Os indicadores que mais de uma tela mostra — uma definição para cada um.

Em 06/11/2026 a Cê Saladas tinha, para a mesma pergunta, números diferentes
conforme a tela aberta:

    receita total         R$ 25.664,50 (loja/Pagamentos)  x  R$ 26.173,08 (Clientes)
    clientes novos (30d)  60 (Visão geral)                 x  67 (Relatórios › Clientes)
    esperando resposta    13 (Início) x 10 (Conversas) x 23/10 (Esperando atendente)
    itens para repor      29 (Visão geral)                 x  4 + 2 (Produtos)
    entrega de campanha   "30 de 561"                      x  "100% entregues"
    comparação c/ média   últimas 4 quintas (pedidos)      x  média de quinta (receita, 28d por pagamento)
    ranking de produtos   o mesmo prato em 2 linhas (agrupado pelo nome gravado)

Cada função abaixo é a regra. A tela que precisar do número chama daqui —
não reescreve o filtro.

Receita continua em `definicoes.py` (`apenas_receita` + `soma_de_venda`);
`receita_pedidos` é só o atalho "quanto deu este queryset".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import CharField, Count, F, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone

from .definicoes import apenas_receita, pedidos_de_receita, soma_de_venda

ZERO = Decimal('0')


# ── Receita total ─────────────────────────────────────────────────────────

def receita_pedidos(queryset, incluir_teste=False) -> Decimal:
    """Receita de um queryset de StoreOrder: pagos, sem cancelado/teste, sem frete.

    É a mesma régua do Histórico de pedidos. A tela de Clientes somava o
    `total_spent` gravado em cada cadastro — número que fica velho (fusão de
    cadastros soma os dois lados, pedido sem cadastro não entra) — e mostrava
    R$ 500 a mais que Pagamentos.
    """
    total = apenas_receita(queryset, incluir_teste=incluir_teste).aggregate(
        t=soma_de_venda(),
    )['t']
    return total or ZERO


# ── Clientes novos ────────────────────────────────────────────────────────

def identidade_do_cliente():
    """Quem é o cliente do pedido: telefone; sem telefone, e-mail."""
    return Coalesce(
        NullIf(F('customer_phone'), Value('')), NullIf(F('customer_email'), Value('')),
        output_field=CharField(),
    )


def clientes_novos(loja, inicio: date, fim: date, incluir_teste=False) -> int:
    """Clientes cuja PRIMEIRA compra paga caiu dentro de [inicio, fim].

    Visão geral contava cadastro criado no período (cadastro sem compra
    entrava; cliente antigo recadastrado também). Relatórios › Clientes
    contava quem comprou só uma vez no período (cliente antigo com um pedido
    no mês virava "novo"). Os dois agora perguntam a mesma coisa.
    """
    primeiras = (
        pedidos_de_receita(loja=loja, incluir_teste=incluir_teste)
        .annotate(_quem=identidade_do_cliente())
        .exclude(_quem=None)
        .values('_quem')
        .annotate(primeira=Min('created_at'))
    )
    contagem = 0
    for linha in primeiras:
        dia = timezone.localtime(linha['primeira']).date()
        if inicio <= dia <= fim:
            contagem += 1
    return contagem


# ── Esperando resposta ────────────────────────────────────────────────────

JANELA_ESPERANDO_RESPOSTA = timedelta(hours=48)


def esperando_resposta(conversas, agora: datetime | None = None):
    """Conversas em que o cliente falou por último e ninguém respondeu — 48 h.

    Janela FIXA de 48 h, em todas as telas: Início, Conversas (filtro
    "Esperando") e Esperando atendente (card e lista). Antes o Início usava
    48 h, a fila humana não tinha janela (o card somava quem escreveu há uma
    semana) e a lista cortava em 24 h — 13, 23 e 10 para a mesma loja.

    "Resposta" é mensagem nossa que não foi automática (o mensageiro não
    grava `last_agent_message_at`): atendente, eco do app Business ou o bot
    respondendo a conversa.
    """
    agora = agora or timezone.now()
    return conversas.filter(
        last_customer_message_at__isnull=False,
        last_customer_message_at__gte=agora - JANELA_ESPERANDO_RESPOSTA,
    ).filter(
        Q(last_agent_message_at__isnull=True)
        | Q(last_customer_message_at__gt=F('last_agent_message_at'))
    )


# ── Itens para repor ──────────────────────────────────────────────────────

def itens_para_repor(produtos):
    """Produtos no ar, que controlam estoque, no mínimo cadastrado ou abaixo.

    `produtos` é um queryset de StoreProduct já recortado na loja. Inclui o
    zerado ("sem estoque") e o que está no fim ("acabando") — a soma dos dois
    cards de Produtos. A Visão geral contava `estoque <= 10` sem olhar se o
    produto controla estoque nem o mínimo dele: 29 contra 6.
    """
    return produtos.filter(
        status='active',
        track_stock=True,
        stock_quantity__lte=F('low_stock_threshold'),
    )


# ── Entrega de campanha ───────────────────────────────────────────────────

def taxa_de_entrega(entregues, publico) -> float | None:
    """Entregues ÷ público total da campanha, em %. None sem público.

    Era entregues ÷ enviadas: uma campanha que mandou 30 de 561 e entregou
    as 30 aparecia "100% entregues".
    """
    publico = int(publico or 0)
    if publico <= 0:
        return None
    return round(min(int(entregues or 0), publico) / publico * 100, 1)


# ── Comparação com a média ────────────────────────────────────────────────

DIAS_NO_PLURAL = ('segundas', 'terças', 'quartas', 'quintas', 'sextas', 'sábados', 'domingos')
SEMANAS_DA_MEDIA = 4


def media_de_referencia(loja, dia: date, semanas: int = SEMANAS_DA_MEDIA, incluir_teste=False) -> dict:
    """A média contra a qual um dia é comparado: as `semanas` mesmas
    dias-da-semana ANTERIORES a `dia` (dia sem venda conta como zero).

    Uma só para o Início. O vigia dizia "36% acima da média das últimas 4
    quintas" (pedidos, só dias com venda) e o resumo da IA "bem abaixo da média
    de quinta (R$ 672,03)" (receita por data de pagamento, 28 dias incluindo o
    próprio dia). `janela` vai escrita no card.
    """
    dias = [dia - timedelta(days=7 * k) for k in range(1, semanas + 1)]
    pedidos = pedidos_de_receita(
        loja=loja, inicio=min(dias), fim=max(dias), incluir_teste=incluir_teste,
    )
    por_dia: dict = {}
    for pedido in pedidos.only('created_at', 'total', 'delivery_fee'):
        d = timezone.localtime(pedido.created_at).date()
        if d not in dias:
            continue
        n, v = por_dia.get(d, (0, ZERO))
        por_dia[d] = (n + 1, v + (pedido.total or ZERO) - (pedido.delivery_fee or ZERO))
    receitas = [por_dia.get(d, (0, ZERO))[1] for d in dias]
    contagens = [por_dia.get(d, (0, ZERO))[0] for d in dias]
    return {
        'receita': (sum(receitas, ZERO) / len(dias)).quantize(Decimal('0.01')),
        'pedidos': round(sum(contagens) / len(dias), 1),
        'dias': [d.isoformat() for d in sorted(dias)],
        'janela': f'últimas {semanas} {DIAS_NO_PLURAL[dia.weekday()]}',
    }


def variacao_pct(valor, media) -> float | None:
    """Quanto `valor` ficou acima (+) ou abaixo (−) da média, em %. None sem base."""
    media = Decimal(str(media or 0))
    if media <= 0:
        return None
    return round(float((Decimal(str(valor or 0)) - media) / media * 100), 1)


# ── Ranking de produtos ───────────────────────────────────────────────────

def ranking_de_produtos(itens, ordenar_por: str = 'receita', limite: int | None = None) -> list:
    """Produtos de um queryset de StoreOrderItem, um por PRODUTO.

    Agrupava pelo nome gravado no item: renomear "Queridinha" ou o mesmo prato
    vendido com nome de combo diferente partia o produto em duas linhas. Agora
    agrupa pelo id; o nome é o ATUAL do produto, com o gravado como reserva
    (produto apagado). Item sem produto agrupa pelo nome gravado.

    Devolve dicts com `produto_id`, `nome`, `quantidade`, `receita`, `pedidos`.
    """
    com_produto = (
        itens.filter(product__isnull=False)
        .values('product_id')
        .annotate(
            nome_atual=Max('product__name'),
            nome_gravado=Max('product_name'),
            quantidade=Coalesce(Sum('quantity'), 0),
            receita=Coalesce(Sum('subtotal'), ZERO),
            pedidos=Count('order', distinct=True),
        )
    )
    sem_produto = (
        itens.filter(product__isnull=True)
        .values('product_name')
        .annotate(
            quantidade=Coalesce(Sum('quantity'), 0),
            receita=Coalesce(Sum('subtotal'), ZERO),
            pedidos=Count('order', distinct=True),
        )
    )
    linhas = [
        {
            'produto_id': str(r['product_id']),
            'nome': r['nome_atual'] or r['nome_gravado'] or '',
            'quantidade': int(r['quantidade'] or 0),
            'receita': r['receita'] or ZERO,
            'pedidos': r['pedidos'],
        }
        for r in com_produto
    ] + [
        {
            'produto_id': None,
            'nome': r['product_name'] or '',
            'quantidade': int(r['quantidade'] or 0),
            'receita': r['receita'] or ZERO,
            'pedidos': r['pedidos'],
        }
        for r in sem_produto
    ]
    chave = 'quantidade' if ordenar_por == 'quantidade' else 'receita'
    outra = 'receita' if chave == 'quantidade' else 'quantidade'
    linhas.sort(key=lambda r: (-r[chave], -r[outra], r['nome']))
    return linhas[:limite] if limite else linhas


# ── Tempos de operação ────────────────────────────────────────────────────

#: Etapa que passou disto não é tempo de operação, é pedido esquecido aberto
#: (o "60716min" da cozinha era um pedido de 42 dias atrás).
LIMITE_ESQUECIDO_MINUTOS = 24 * 60


def percentil(valores, p: float) -> float | None:
    """Percentil com interpolação linear (o mesmo do numpy/Excel).

    O cálculo antigo pegava o elemento de índice `round(0.9 × (n−1))`,
    que arredonda para baixo da posição real e subestima o p90 em amostra
    pequena.
    """
    ordenados = sorted(valores)
    if not ordenados:
        return None
    pos = (len(ordenados) - 1) * p
    baixo = math.floor(pos)
    alto = math.ceil(pos)
    if baixo == alto:
        return float(ordenados[baixo])
    return float(ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (pos - baixo))


@dataclass
class TempoDeEtapa:
    """Média e p90 de uma etapa, sobre a MESMA amostra, sem os esquecidos."""

    minutos: list = field(default_factory=list)
    esquecidos: int = 0

    def registrar(self, minutos: float) -> None:
        if minutos < 0:
            return
        if minutos > LIMITE_ESQUECIDO_MINUTOS:
            self.esquecidos += 1
        else:
            self.minutos.append(minutos)

    def resumo(self) -> dict:
        n = len(self.minutos)
        return {
            'count': n,
            'avg_minutes': round(sum(self.minutos) / n, 1) if n else None,
            'p90_minutes': round(percentil(self.minutos, 0.9), 1) if n else None,
            'esquecidos': self.esquecidos,
        }
