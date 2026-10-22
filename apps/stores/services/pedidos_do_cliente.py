"""Qual pedido deste cliente nesta loja é este: 1º, 2º, 5º...

Uma conta só para o detalhe do painel e para a comanda (print agent e
impressão pelo painel). Antes o detalhe contava TODOS os pedidos do telefone:
cancelado, PIX abandonado e até os feitos depois — reimprimir um pedido
antigo dizia "12º".

Regra: pedidos ANTERIORES que valeram (pagos, não cancelados, não teste —
`apenas_receita`) + este. Este conta mesmo sem pagamento: a comanda sai antes
do cartão na entrega ser cobrado. Telefone por variantes (wa_id vem sem o
nono dígito).
"""
from apps.core.utils import phone_variants


def numero_do_pedido_do_cliente(pedido):
    """1 para cliente novo; None sem telefone."""
    variantes = phone_variants(pedido.customer_phone or '')
    if not variantes:
        return None
    from apps.stores.metrics import apenas_receita
    from apps.stores.models import StoreOrder

    anteriores = StoreOrder.objects.filter(
        store_id=pedido.store_id,
        customer_phone__in=variantes,
        created_at__lt=pedido.created_at,
    ).exclude(pk=pedido.pk)
    return apenas_receita(anteriores).count() + 1
