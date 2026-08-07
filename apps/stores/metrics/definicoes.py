"""O que conta como dinheiro.

Uma regra, um lugar. Antes disto, seis arquivos respondiam a esta pergunta cada
um do seu jeito e davam três respostas diferentes para o mesmo dia:

    BI/analytics   payment_status='paid'               -> R$ 2.324,35
    resumo de IA   exclui cancelled/refunded/failed    -> R$ 2.419,35
    gráfico 30d    sem filtro nenhum                   -> R$ 5.056,42
    correto        pago E não cancelado                -> R$ 2.324,35

O gráfico da home mostrava mais que o dobro do faturamento real porque somava
os 21 pedidos cancelados. E nenhum dos três excluía os pedidos de teste do
dono, que eram ~40% do volume.

Qualquer tela, relatório ou export que fale de DINHEIRO usa este módulo.
Contagem operacional (fila da cozinha, KDS, histórico do cliente) NÃO usa —
lá o pedido cancelado e o de teste precisam aparecer. Ver `series.contagem_operacional`.
"""
from django.db.models import Q
from django.db.models.functions import Coalesce

# Status em que o pedido deixa de ser receita, independente do pagamento.
STATUS_SEM_RECEITA = frozenset({'cancelled', 'refunded', 'failed'})

# Chave em StoreOrder.metadata que marca pedido de teste do próprio dono.
FLAG_PEDIDO_TESTE = 'is_test'


def eixo_de_receita():
    """A data que define A QUE DIA a receita pertence.

    `paid_at` — o dia em que o dinheiro entrou — com fallback para `created_at`
    quando não há registro de pagamento pelo gateway (dinheiro na entrega,
    baixa manual). Sem o fallback esses pedidos sumiriam de qualquer série.

    Existe porque cada tela escolhia um eixo: `/orders/stats/` agrupava por
    `created_at` e o painel por `paid_at`. Um pedido feito 31/07 23h40 e pago
    01/08 00h05 aparecia em dias diferentes nas duas telas — o total batia, a
    distribuição não, e não dava para conciliar com o extrato.

    IMPORTANTE: use sem `tzinfo=` no TruncDate. Assim o Django agrupa pelo
    TIME_ZONE do projeto (America/Sao_Paulo). Forçar UTC jogava toda venda
    depois das 21h para o dia seguinte — justamente o pico do delivery.
    """
    return Coalesce('paid_at', 'created_at')


def _q_pedido_de_teste(prefixo=''):
    """Q que casa SÓ pedido marcado como teste.

    Um `exclude(metadata__is_test=True)` direto descartaria também os pedidos
    em que a chave não existe: o lookup vira NULL, e `NOT NULL` é NULL em SQL —
    ou seja, sumiria com o faturamento inteiro. Daí o has_key explícito.
    """
    return (
        Q(**{f'{prefixo}metadata__has_key': FLAG_PEDIDO_TESTE})
        & Q(**{f'{prefixo}metadata__{FLAG_PEDIDO_TESTE}': True})
    )


def apenas_receita(queryset, incluir_teste=False):
    """Aplica a regra de receita a um queryset de StoreOrder já montado.

    Use quando você já tem o queryset (com joins, período, etc.) e só precisa
    da regra — evita reconstruir a query do zero.
    """
    qs = queryset.filter(payment_status='paid').exclude(status__in=STATUS_SEM_RECEITA)
    if not incluir_teste:
        qs = qs.exclude(_q_pedido_de_teste())
    return qs


def pedidos_de_receita(loja=None, inicio=None, fim=None, incluir_teste=False, queryset=None):
    """Pedidos que contam como faturamento.

    Regra: pago **e** não cancelado/estornado/falho **e** não é teste.

    `loja`/`inicio`/`fim` são atalhos; para casos com joins, passe `queryset`.
    `inicio` e `fim` são datas (não datetimes) no fuso da loja.
    """
    if queryset is None:
        from apps.stores.models import StoreOrder
        queryset = StoreOrder.objects.all()
    if loja is not None:
        queryset = queryset.filter(store=loja)
    # Filtra pelo MESMO eixo em que a receita é agrupada. Filtrar por
    # created_at e agrupar por paid_at deixava pedido pago dentro da janela
    # fora do resultado, e vice-versa.
    if inicio is not None or fim is not None:
        queryset = queryset.annotate(_data_receita=eixo_de_receita())
    if inicio is not None and fim is not None:
        queryset = queryset.filter(_data_receita__date__range=(inicio, fim))
    elif inicio is not None:
        queryset = queryset.filter(_data_receita__date__gte=inicio)
    elif fim is not None:
        queryset = queryset.filter(_data_receita__date__lte=fim)
    return apenas_receita(queryset, incluir_teste=incluir_teste)


def itens_de_receita(loja=None, inicio=None, fim=None, incluir_teste=False):
    """StoreOrderItem dos pedidos que contam como faturamento (top produtos)."""
    from apps.stores.models import StoreOrderItem
    qs = StoreOrderItem.objects.filter(
        order__payment_status='paid',
    ).exclude(order__status__in=STATUS_SEM_RECEITA)
    if not incluir_teste:
        qs = qs.exclude(_q_pedido_de_teste(prefixo='order__'))
    if loja is not None:
        qs = qs.filter(order__store=loja)
    if inicio is not None or fim is not None:
        qs = qs.annotate(_data_receita=Coalesce('order__paid_at', 'order__created_at'))
    if inicio is not None and fim is not None:
        qs = qs.filter(_data_receita__date__range=(inicio, fim))
    elif inicio is not None:
        qs = qs.filter(_data_receita__date__gte=inicio)
    elif fim is not None:
        qs = qs.filter(_data_receita__date__lte=fim)
    return qs


def eh_pedido_de_teste(pedido) -> bool:
    """True se o pedido foi marcado como teste do dono."""
    metadata = getattr(pedido, 'metadata', None) or {}
    return bool(metadata.get(FLAG_PEDIDO_TESTE))


def marcar_como_teste(pedido, salvar=True):
    """Marca o pedido como teste preservando o resto do metadata."""
    metadata = dict(getattr(pedido, 'metadata', None) or {})
    metadata[FLAG_PEDIDO_TESTE] = True
    pedido.metadata = metadata
    if salvar:
        pedido.save(update_fields=['metadata'])
    return pedido
