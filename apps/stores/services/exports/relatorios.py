"""
Agregações dos relatórios que o dono usa para decidir.

Todos os números de dinheiro passam por `pedidos_de_receita` — o SSOT que exclui
cancelado, estornado, falho e pedido de teste. Sem isso um relatório de
faturamento mostraria um número e a home do painel outro, que foi exatamente o
problema que o SSOT nasceu para resolver.

Contagem operacional (quantos pedidos entraram) é outra coisa e não usa este
módulo.
"""
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce, TruncDate

from apps.stores.metrics import eixo_de_receita, pedidos_de_receita

_DEC = DecimalField(max_digits=12, decimal_places=2)

# O banco guarda o código cru do gateway/checkout. Num relatório que o dono lê
# (e manda para o contador), "cash" e "pickup" não dizem nada.
_ROTULO_PAGAMENTO = {
    'cash': 'Dinheiro',
    'pix': 'PIX',
    'credit_card': 'Cartão de crédito',
    'debit_card': 'Cartão de débito',
    'card': 'Cartão',
    'mercadopago': 'Mercado Pago',
    'meal_voucher': 'Vale-refeição',
    'bank_transfer': 'Transferência',
    'other': 'Outro',
}

_ROTULO_ENTREGA = {
    'delivery': 'Entrega',
    'pickup': 'Retirada no local',
    'dine_in': 'Consumo no local',
    'counter': 'Balcão',
    'table': 'Mesa',
}


def _rotulo(codigo, mapa):
    """Código do banco → nome legível. Desconhecido vira o próprio código
    capitalizado, para não sumir do relatório nem virar 'None'."""
    if not codigo:
        return 'Não informado'
    return mapa.get(str(codigo).lower(), str(codigo).replace('_', ' ').capitalize())


def _zero():
    return Coalesce(Sum('total'), Decimal('0'), output_field=_DEC)


def vendas_por_item(store, inicio, fim, incluir_teste=False):
    """Quanto cada produto vendeu, do maior faturamento para o menor.

    Responde "o que realmente vende" — que não é a mesma pergunta que "o que mais
    sai em quantidade": um item barato pode liderar em unidades e ser irrelevante
    no caixa. Por isso as duas colunas aparecem juntas, ordenadas por receita.

    Inclui participação acumulada (curva ABC): com ela o dono vê que ~20% dos
    itens costumam responder por ~80% do faturamento, e é neles que mexer preço,
    foto ou destaque muda o resultado.
    """
    from apps.stores.models import StoreOrderItem

    pedidos = pedidos_de_receita(loja=store, inicio=inicio, fim=fim, incluir_teste=incluir_teste)
    itens = (
        StoreOrderItem.objects.filter(order__in=pedidos)
        .values('product_name', 'variant_name')
        .annotate(
            quantidade=Coalesce(Sum('quantity'), 0),
            receita=Coalesce(Sum('subtotal'), Decimal('0'), output_field=_DEC),
            pedidos=Count('order', distinct=True),
        )
        .order_by('-receita')
    )

    linhas = []
    total_receita = sum((i['receita'] for i in itens), Decimal('0'))
    acumulado = Decimal('0')
    for i in itens:
        receita = i['receita'] or Decimal('0')
        acumulado += receita
        nome = i['product_name']
        if i['variant_name']:
            nome = f"{nome} ({i['variant_name']})"
        linhas.append({
            'produto': nome,
            'quantidade': i['quantidade'] or 0,
            'pedidos': i['pedidos'] or 0,
            'receita': receita,
            # preço médio praticado — revela desconto/combo puxando a margem
            'preco_medio': (receita / i['quantidade']) if i['quantidade'] else Decimal('0'),
            'part_receita': (receita / total_receita) if total_receita else Decimal('0'),
            'acumulado': (acumulado / total_receita) if total_receita else Decimal('0'),
        })
    return linhas


def faturamento_por_dia(store, inicio, fim, incluir_teste=False):
    """Série diária de faturamento no MESMO eixo do painel (paid_at c/ fallback).

    Agrupar por `created_at` aqui faria o relatório divergir do gráfico da home
    para todo pedido criado num dia e pago no outro.
    """
    pedidos = pedidos_de_receita(loja=store, inicio=inicio, fim=fim, incluir_teste=incluir_teste)
    linhas = (
        pedidos.annotate(dia=TruncDate(eixo_de_receita()))
        .values('dia')
        .annotate(
            pedidos=Count('id'),
            receita=_zero(),
            ticket_medio=Coalesce(Avg('total'), Decimal('0'), output_field=_DEC),
            entrega=Coalesce(Sum('delivery_fee'), Decimal('0'), output_field=_DEC),
            desconto=Coalesce(Sum('discount'), Decimal('0'), output_field=_DEC),
        )
        .order_by('dia')
    )
    return [
        {
            'dia': l['dia'],
            'pedidos': l['pedidos'],
            'receita': l['receita'],
            'ticket_medio': l['ticket_medio'],
            'entrega': l['entrega'],
            'desconto': l['desconto'],
        }
        for l in linhas
    ]


def faturamento_por_pagamento(store, inicio, fim, incluir_teste=False):
    """Quebra por meio de pagamento — para conciliar com o extrato do gateway."""
    pedidos = pedidos_de_receita(loja=store, inicio=inicio, fim=fim, incluir_teste=incluir_teste)
    linhas = (
        pedidos.values('payment_method')
        .annotate(pedidos=Count('id'), receita=_zero())
        .order_by('-receita')
    )
    total = sum((l['receita'] for l in linhas), Decimal('0'))
    return [
        {
            'metodo': _rotulo(l['payment_method'], _ROTULO_PAGAMENTO),
            'pedidos': l['pedidos'],
            'receita': l['receita'],
            'participacao': (l['receita'] / total) if total else Decimal('0'),
        }
        for l in linhas
    ]


def faturamento_por_entrega(store, inicio, fim, incluir_teste=False):
    """Entrega x retirada x balcão: onde o volume acontece."""
    pedidos = pedidos_de_receita(loja=store, inicio=inicio, fim=fim, incluir_teste=incluir_teste)
    linhas = (
        pedidos.values('delivery_method')
        .annotate(
            pedidos=Count('id'),
            receita=_zero(),
            taxa=Coalesce(Sum('delivery_fee'), Decimal('0'), output_field=_DEC),
        )
        .order_by('-receita')
    )
    return [
        {
            'modalidade': _rotulo(l['delivery_method'], _ROTULO_ENTREGA),
            'pedidos': l['pedidos'],
            'receita': l['receita'],
            'taxa_entrega': l['taxa'],
        }
        for l in linhas
    ]


def resumo_faturamento(store, inicio, fim, incluir_teste=False):
    """Números de topo — o que vai na primeira linha do relatório."""
    pedidos = pedidos_de_receita(loja=store, inicio=inicio, fim=fim, incluir_teste=incluir_teste)
    agregado = pedidos.aggregate(
        pedidos=Count('id'),
        receita=_zero(),
        ticket_medio=Coalesce(Avg('total'), Decimal('0'), output_field=_DEC),
        entrega=Coalesce(Sum('delivery_fee'), Decimal('0'), output_field=_DEC),
        desconto=Coalesce(Sum('discount'), Decimal('0'), output_field=_DEC),
    )
    dias = (fim - inicio).days + 1 if inicio and fim else 0
    agregado['media_diaria'] = (agregado['receita'] / dias) if dias else Decimal('0')
    agregado['dias'] = dias
    return agregado
