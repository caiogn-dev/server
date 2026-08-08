"""Como o dinheiro se distribui — agregação sobre os pedidos de receita.

Separação que o código não fazia e que causava o pior tipo de bug silencioso:

- **receita** responde "quanto entrou". Exclui cancelado, estornado, não pago e
  pedido de teste. É o que vai para o card, o relatório e o export.
- **contagem operacional** responde "quanto passou pela cozinha". Inclui tudo,
  porque o pedido cancelado existiu, ocupou fogão e precisa aparecer na fila.

As duas coisas viviam na mesma função com um filtro opcional, e telas
diferentes passavam o filtro diferente. Agora são funções com nomes distintos:
não dá para confundir por acidente.
"""
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from .definicoes import apenas_receita, eixo_de_receita, pedidos_de_receita
from .janelas import Janela

GRANULARIDADES = {
    'dia': TruncDate,
    'semana': TruncWeek,
    'mes': TruncMonth,
}

ZERO = Decimal('0.00')


def _decimal(valor) -> Decimal:
    return Decimal(str(valor)) if valor is not None else ZERO


def totais(loja, janela: Janela, incluir_teste=False) -> dict:
    """Agregado de RECEITA no período. Fala de dinheiro."""
    qs = pedidos_de_receita(
        loja=loja, inicio=janela.inicio, fim=janela.fim, incluir_teste=incluir_teste,
    )
    agg = qs.aggregate(
        receita=Sum('total'),
        pedidos=Count('id'),
        ticket_medio=Avg('total'),
        frete=Sum('delivery_fee'),
        desconto=Sum('discount'),
    )
    return {
        'receita': _decimal(agg['receita']),
        'pedidos': agg['pedidos'] or 0,
        'ticket_medio': _decimal(agg['ticket_medio']),
        'frete': _decimal(agg['frete']),
        'desconto': _decimal(agg['desconto']),
    }


def resumo_de_lista(queryset, incluir_teste=False) -> dict:
    """Totais de um recorte JÁ FILTRADO de pedidos — o que a tela está mostrando.

    Diferente de `totais()`: lá a janela e a loja montam a consulta; aqui o
    queryset vem pronto da view, com os filtros que o operador escolheu
    (período, status, canal, busca).

    Existe porque o resumo de uma lista NÃO pode ser uma consulta paralela. Se
    o card soma por `paid_at` enquanto a lista mostra por `created_at`, o
    operador vê "R$ 900" acima de linhas que somam R$ 850 — e a divergência
    entre dois números na mesma tela destrói a confiança nos dois.

    Devolve volume (inclui cancelado e não pago, porque a lista os mostra) E
    dinheiro (só o que faturou), separados e rotulados.
    """
    from apps.stores.models import StoreOrder

    faturando = apenas_receita(queryset, incluir_teste=incluir_teste)
    agg = faturando.aggregate(receita=Sum('total'), pedidos=Count('id'))

    receita = _decimal(agg['receita'])
    pagos = agg['pedidos'] or 0

    return {
        'pedidos': queryset.count(),
        'cancelados': queryset.filter(status=StoreOrder.OrderStatus.CANCELLED).count(),
        'pedidos_faturados': pagos,
        'receita': receita,
        # Divide pelos pedidos que FATURARAM. Dividir pelo total (com cancelado
        # e não pago dentro) derruba o número e mente sobre a venda média.
        #
        # `None` sem venda: "ticket médio R$ 0,00" lê como venda de graça.
        'ticket_medio': (receita / pagos).quantize(Decimal('0.01')) if pagos else None,
    }


def quebra_de_lista(queryset, campo: str, incluir_teste=False) -> list:
    """Receita do recorte agrupada por um campo (pagamento, canal).

    Mesmo queryset filtrado do `resumo_de_lista`, então as partes somam o todo
    — e é isso que permite usar a quebra para fechar o caixa.
    """
    faturando = apenas_receita(queryset, incluir_teste=incluir_teste)
    return [
        {
            'chave': linha[campo] or 'nao_informado',
            'pedidos': linha['n'],
            'total': _decimal(linha['soma']),
        }
        for linha in faturando.values(campo).annotate(
            n=Count('id'), soma=Sum('total')
        ).order_by('-soma')
    ]


def contagem_operacional(loja, janela: Janela) -> dict:
    """Volume que passou pela operação. NÃO é faturamento.

    Inclui cancelado e não pago de propósito: a fila da cozinha e o histórico
    do cliente precisam mostrar o pedido que existiu, mesmo que não virou
    dinheiro. Nunca some `total` daqui para falar de receita.
    """
    from apps.stores.models import StoreOrder

    qs = (
        StoreOrder.objects
        .filter(store=loja)
        .annotate(_data=eixo_de_receita())
        .filter(_data__date__range=(janela.inicio, janela.fim))
    )
    por_status = dict(
        qs.values('status').annotate(n=Count('id')).values_list('status', 'n')
    )
    return {'pedidos': qs.count(), 'por_status': por_status}


def serie_temporal(loja, janela: Janela, granularidade='dia', incluir_teste=False) -> list:
    """Receita distribuída no tempo.

    Agrupa pelo MESMO eixo em que filtra (data do pagamento) — filtrar por um e
    agrupar por outro deixava pedido dentro da janela fora do gráfico.

    Sem `tzinfo=` no Trunc: assim o Django agrupa pelo TIME_ZONE do projeto.
    Forçar UTC jogava toda venda depois das 21h para o dia seguinte.
    """
    trunc = GRANULARIDADES.get(granularidade)
    if trunc is None:
        raise ValueError(
            f'granularidade inválida: {granularidade!r}. '
            f'Use uma de {sorted(GRANULARIDADES)}'
        )

    qs = pedidos_de_receita(
        loja=loja, inicio=janela.inicio, fim=janela.fim, incluir_teste=incluir_teste,
    )
    linhas = (
        qs.annotate(periodo=trunc(eixo_de_receita()))
        .values('periodo')
        .annotate(
            receita=Sum('total'),
            pedidos=Count('id'),
            ticket_medio=Avg('total'),
            frete=Sum('delivery_fee'),
            desconto=Sum('discount'),
        )
        .order_by('periodo')
    )
    return [
        {
            'periodo': linha['periodo'],
            'receita': _decimal(linha['receita']),
            'pedidos': linha['pedidos'] or 0,
            'ticket_medio': _decimal(linha['ticket_medio']),
            'frete': _decimal(linha['frete']),
            'desconto': _decimal(linha['desconto']),
        }
        for linha in linhas
    ]


def serie_completa(loja, janela: Janela, granularidade='dia', incluir_teste=False) -> list:
    """Igual a `serie_temporal`, mas com os dias sem venda preenchidos com zero.

    Gráfico com dias faltando mente sobre a tendência: uma semana com vendas só
    na sexta vira uma linha reta se os zeros não estiverem lá.
    Só faz sentido em granularidade diária.
    """
    from datetime import timedelta

    if granularidade != 'dia':
        return serie_temporal(loja, janela, granularidade, incluir_teste)

    por_dia = {
        ponto['periodo']: ponto
        for ponto in serie_temporal(loja, janela, 'dia', incluir_teste)
    }
    saida = []
    dia = janela.inicio
    while dia <= janela.fim:
        saida.append(por_dia.get(dia, {
            'periodo': dia,
            'receita': ZERO,
            'pedidos': 0,
            'ticket_medio': ZERO,
            'frete': ZERO,
            'desconto': ZERO,
        }))
        dia += timedelta(days=1)
    return saida


def top_produtos(loja, janela: Janela, limite=10, incluir_teste=False) -> list:
    """Produtos que mais faturaram no período."""
    from .definicoes import itens_de_receita

    linhas = (
        itens_de_receita(
            loja=loja, inicio=janela.inicio, fim=janela.fim, incluir_teste=incluir_teste,
        )
        .values('product_id', 'product__name')
        .annotate(receita=Sum('subtotal'), unidades=Sum('quantity'))
        .order_by('-receita')[:limite]
    )
    return [
        {
            'produto_id': linha['product_id'],
            'nome': linha['product__name'],
            'receita': _decimal(linha['receita']),
            'unidades': linha['unidades'] or 0,
        }
        for linha in linhas
    ]


def comparar_periodo(loja, janela: Janela, incluir_teste=False) -> dict:
    """Compara a janela com a anterior, do mesmo tamanho.

    Devolve `variacao_pct=None` quando o período anterior foi zero — dividir
    por zero ali produzia "+∞%" ou um 100% que não significa nada.
    """
    from .janelas import janela_anterior

    atual = totais(loja, janela, incluir_teste)
    anterior = totais(loja, janela_anterior(janela), incluir_teste)
    delta = atual['receita'] - anterior['receita']
    variacao = (
        (delta / anterior['receita'] * 100) if anterior['receita'] else None
    )
    return {
        'atual': atual,
        'anterior': anterior,
        'delta': delta,
        'variacao_pct': variacao,
    }
