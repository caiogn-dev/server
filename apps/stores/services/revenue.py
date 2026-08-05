"""SSOT de receita: o que conta como faturamento e o que não conta.

Existiam três definições diferentes espalhadas, e cada tela do painel mostrava um
número. Para a Cê Saladas, no mesmo dia:

    BI/analytics   payment_status='paid'               -> R$ 2.324,35
    resumo de IA   exclui cancelled/refunded/failed    -> R$ 2.419,35
    gráfico 30d    sem filtro nenhum                   -> R$ 5.056,42  ← na home
    correto        pago E não cancelado                -> R$ 2.324,35

O gráfico da home mostrava mais que o dobro do faturamento real porque somava os
21 pedidos cancelados. E nenhum dos três excluía os pedidos de teste do dono, que
eram ~40% do volume.

Qualquer tela, relatório ou export que fale de dinheiro deve usar `revenue_orders`.
Contagem operacional (fila da cozinha, KDS, histórico do cliente) NÃO deve — lá o
pedido cancelado e o de teste precisam aparecer.
"""
from django.db.models import Q
from django.db.models.functions import Coalesce

# Status em que o pedido deixa de ser receita, independente do pagamento.
NON_REVENUE_STATUSES = frozenset({'cancelled', 'refunded', 'failed'})

# Chave em StoreOrder.metadata que marca pedido de teste do próprio dono.
TEST_ORDER_FLAG = 'is_test'


def revenue_date_field():
    """Expressão da data que define A QUE DIA a receita pertence.

    É `paid_at` — o dia em que o dinheiro entrou — com fallback para `created_at`
    quando não há registro de pagamento pelo gateway (dinheiro na entrega, baixa
    manual). Sem o fallback esses pedidos sumiriam de qualquer série temporal.

    Existia porque cada tela escolhia um eixo: o forecast agrupava por
    `created_at` e o painel por `paid_at`. Um pedido criado em 31/07 e pago em
    01/08 aparecia em dias diferentes nas duas telas — o total batia, a
    distribuição não, e não dava para conciliar.

    IMPORTANTE: use sem `tzinfo=` no TruncDate. Assim o Django agrupa pelo
    TIME_ZONE do projeto (America/Sao_Paulo). Forçar UTC jogava toda venda
    depois das 21h para o dia seguinte — justamente o pico do delivery.
    """
    return Coalesce('paid_at', 'created_at')


def is_test_order(order) -> bool:
    """True se o pedido foi marcado como teste."""
    metadata = getattr(order, 'metadata', None) or {}
    return bool(metadata.get(TEST_ORDER_FLAG))


def mark_as_test(order, save=True):
    """Marca o pedido como teste preservando o resto do metadata."""
    metadata = dict(getattr(order, 'metadata', None) or {})
    metadata[TEST_ORDER_FLAG] = True
    order.metadata = metadata
    if save:
        order.save(update_fields=['metadata'])
    return order


def exclude_non_revenue(queryset, include_test=False):
    """Aplica o filtro de receita a um queryset de StoreOrder já construído.

    Use quando você já tem o queryset (com joins, período, etc.) e só precisa da
    regra de receita — evita reconstruir a query do zero.
    """
    qs = queryset.filter(payment_status='paid').exclude(status__in=NON_REVENUE_STATUSES)
    if not include_test:
        qs = qs.exclude(_test_order_q())
    return qs


def _test_order_q(prefix=''):
    """Q que casa SÓ pedido marcado como teste.

    Um `exclude(metadata__is_test=True)` direto descartaria também os pedidos em
    que a chave não existe: o lookup vira NULL, e `NOT NULL` é NULL em SQL — ou
    seja, sumiria com o faturamento inteiro. Por isso o has_key explícito.
    """
    return (
        Q(**{f'{prefix}metadata__has_key': TEST_ORDER_FLAG})
        & Q(**{f'{prefix}metadata__{TEST_ORDER_FLAG}': True})
    )


def revenue_orders(store=None, start=None, end=None, include_test=False, queryset=None):
    """Pedidos que contam como faturamento.

    Regra: pago **e** não cancelado/estornado/falho **e** não é teste.

    store/start/end são atalhos; para casos com joins, passe `queryset`.
    """
    if queryset is None:
        from apps.stores.models import StoreOrder
        queryset = StoreOrder.objects.all()
    if store is not None:
        queryset = queryset.filter(store=store)
    # Filtra pelo MESMO eixo em que a receita é agrupada (paid_at, com fallback).
    # Filtrar por created_at e agrupar por paid_at deixava pedido pago dentro da
    # janela fora do resultado, e vice-versa.
    if start is not None or end is not None:
        queryset = queryset.annotate(_rev_dt=revenue_date_field())
    if start is not None and end is not None:
        queryset = queryset.filter(_rev_dt__date__range=(start, end))
    elif start is not None:
        queryset = queryset.filter(_rev_dt__date__gte=start)
    return exclude_non_revenue(queryset, include_test=include_test)


def revenue_items(store=None, start=None, end=None, include_test=False):
    """StoreOrderItem dos pedidos que contam como faturamento (para top produtos)."""
    from apps.stores.models import StoreOrderItem
    qs = StoreOrderItem.objects.filter(
        order__payment_status='paid',
    ).exclude(order__status__in=NON_REVENUE_STATUSES)
    if not include_test:
        qs = qs.exclude(_test_order_q(prefix='order__'))
    if store is not None:
        qs = qs.filter(order__store=store)
    if start is not None or end is not None:
        qs = qs.annotate(_rev_dt=Coalesce('order__paid_at', 'order__created_at'))
    if start is not None and end is not None:
        qs = qs.filter(_rev_dt__date__range=(start, end))
    elif start is not None:
        qs = qs.filter(_rev_dt__date__gte=start)
    return qs
