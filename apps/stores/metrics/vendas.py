"""Vendas do período — volume E dinheiro na mesma janela, pela regra do Histórico.

Existe por causa de 06/11/2026: em Relatórios › Vendas, com "Ontem", o card
"Pedidos no período" mostrava pedidos de HOJE e "Cancelados" o total desde
sempre ("7100,0% do total"). Metade da tela lia `core/dashboard/charts/?days=1`
(que não conhece período nem fuso da loja) e a outra metade `reports/revenue/`.

A régua é a do Histórico de pedidos (`StoreOrderViewSet.resumo`), que o dono já
confere contra o extrato:

- recorte: pedidos da loja pela data de ENTRADA (`created_at`) no fuso da loja,
  sem venda de saldo (`source='carteira'`, que o Histórico também não lista);
- `pedidos` e `cancelados` contam tudo que entrou no recorte;
- `pagos`, `faturamento` e `ticket_medio` seguem `apenas_receita` (pago, sem
  cancelado/estornado, sem teste) e somam venda SEM frete.

Qualquer tela que precise desses números chama `vendas_do_periodo` — não refaz
a conta.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.db.models.functions import TruncDate

from .definicoes import apenas_receita, soma_de_venda
from .janelas import Janela
from .series import resumo_de_lista

# Origens que o Histórico de pedidos esconde por padrão (ver StoreOrderViewSet).
FONTES_FORA_DO_HISTORICO = ('carteira',)


def recorte_do_historico(loja, janela: Janela):
    """Os pedidos que o Histórico mostra para a loja na janela, sem outros filtros."""
    from apps.stores.models import StoreOrder

    return (
        StoreOrder.objects
        .filter(store=loja, created_at__date__range=(janela.inicio, janela.fim))
        .exclude(source__in=FONTES_FORA_DO_HISTORICO)
    )


def _pct(parte: int, todo: int) -> float:
    """Percentual de 0 a 100 com uma casa. Sem base, 0 — nunca passa de 100."""
    if not todo:
        return 0.0
    return round(min(parte, todo) * 100 / todo, 1)


def vendas_do_periodo(loja, janela: Janela) -> dict:
    """Todos os números do relatório de Vendas, numa janela só.

    Devolve:
      pedidos, pagos, cancelados, cancelados_pct, reembolsados,
      faturamento (Decimal, sem frete), frete, ticket_medio (Decimal ou None),
      por_status {status: n}, por_dia [{data, pedidos, pagos, cancelados, faturamento}]
      (dias sem pedido aparecem com zero).
    """
    from apps.stores.models import StoreOrder

    qs = recorte_do_historico(loja, janela)
    resumo = resumo_de_lista(qs)

    por_status = dict(
        qs.order_by().values('status').annotate(n=Count('id')).values_list('status', 'n')
    )

    cancelado = StoreOrder.OrderStatus.CANCELLED
    faturando = apenas_receita(qs)
    volume = {
        linha['dia']: linha
        for linha in qs.order_by().annotate(dia=TruncDate('created_at'))
        .values('dia')
        .annotate(pedidos=Count('id'), cancelados=Count('id', filter=Q(status=cancelado)))
    }
    dinheiro = {
        linha['dia']: linha
        for linha in faturando.order_by().annotate(dia=TruncDate('created_at'))
        .values('dia')
        .annotate(pagos=Count('id'), faturamento=soma_de_venda())
    }

    por_dia = []
    dia = janela.inicio
    while dia <= janela.fim:
        v = volume.get(dia, {})
        d = dinheiro.get(dia, {})
        por_dia.append({
            'data': dia,
            'pedidos': v.get('pedidos', 0),
            'pagos': d.get('pagos', 0),
            'cancelados': v.get('cancelados', 0),
            'faturamento': d.get('faturamento') or Decimal('0.00'),
        })
        dia += timedelta(days=1)

    return {
        'inicio': janela.inicio,
        'fim': janela.fim,
        'pedidos': resumo['pedidos'],
        'pagos': resumo['pedidos_faturados'],
        'cancelados': resumo['cancelados'],
        'cancelados_pct': _pct(resumo['cancelados'], resumo['pedidos']),
        'reembolsados': resumo['reembolsados'],
        'faturamento': resumo['receita'],
        'frete': resumo['frete'],
        'ticket_medio': resumo['ticket_medio'],
        'por_status': por_status,
        'por_dia': por_dia,
    }
