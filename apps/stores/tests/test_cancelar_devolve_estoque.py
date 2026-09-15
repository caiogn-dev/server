"""Cancelar devolve o estoque que a venda baixou — por qualquer caminho.

O botão "Cancelar" da tela de detalhe do pedido no painel chama
`update_status('cancelled')`, que não devolvia estoque (só o `/cancel/` da lista
devolvia). E havia duas devoluções diferentes: `cancel_order` ignorava variante
e `sold_count`; `CheckoutService._restore_stock` (webhook) ignorava combo.
A venda baixa os três (produto+sold_count, variante, combo); a devolução é uma só.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import (
    Store, StoreCombo, StoreOrder, StoreOrderComboItem, StoreOrderItem,
    StoreProduct, StoreProductVariant,
)
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.order_service import OrderService

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_estoque_cancel', password='x')
    return Store.objects.create(owner=dono, name='Loja Estoque', slug='loja-estoque-cancel')


@pytest.fixture
def pedido(loja):
    """Pedido já com a baixa feita: produto 8/2 vendidos, variante 3, combo 4."""
    produto = StoreProduct.objects.create(
        store=loja, name='Marmita', slug='marmita', price=Decimal('20'),
        track_stock=True, stock_quantity=8, sold_count=2,
    )
    com_variante = StoreProduct.objects.create(
        store=loja, name='Suco', slug='suco', price=Decimal('8'), track_stock=True, stock_quantity=0,
    )
    variante = StoreProductVariant.objects.create(product=com_variante, name='500ml', stock_quantity=3)
    combo = StoreCombo.objects.create(
        store=loja, name='Combo', slug='combo', price=Decimal('30'), track_stock=True, stock_quantity=4,
    )
    ordem = StoreOrder.objects.create(
        store=loja, total=Decimal('78'), subtotal=Decimal('78'),
        status='confirmed', payment_status='paid', payment_method='cash',
    )
    StoreOrderItem.objects.create(order=ordem, product=produto, product_name='Marmita',
                                  unit_price=Decimal('20'), quantity=2, subtotal=Decimal('40'))
    StoreOrderItem.objects.create(order=ordem, product=com_variante, variant=variante, product_name='Suco',
                                  unit_price=Decimal('8'), quantity=1, subtotal=Decimal('8'))
    item_combo = StoreOrderItem.objects.create(order=ordem, product=None, product_name='Combo: Combo',
                                               unit_price=Decimal('30'), quantity=1, subtotal=Decimal('30'))
    StoreOrderComboItem.objects.create(order=ordem, order_item=item_combo, combo=combo, quantity=1)
    return ordem, produto, variante, combo


def _estoques(produto, variante, combo):
    for obj in (produto, variante, combo):
        obj.refresh_from_db()
    return produto.stock_quantity, produto.sold_count, variante.stock_quantity, combo.stock_quantity


@pytest.mark.django_db
class TestCancelarDevolveEstoque:

    def test_botao_cancelar_do_detalhe_devolve(self, pedido):
        ordem, produto, variante, combo = pedido

        OrderService().update_status(ordem, 'cancelled', notify_customer=False)

        assert _estoques(produto, variante, combo) == (10, 0, 4, 5)

    def test_cancel_order_devolve_variante_vendidos_e_combo(self, pedido):
        ordem, produto, variante, combo = pedido

        OrderService().cancel_order(ordem)

        assert _estoques(produto, variante, combo) == (10, 0, 4, 5)

    def test_webhook_devolve_combo_tambem(self, pedido):
        ordem, produto, variante, combo = pedido

        CheckoutService._restore_stock(ordem)

        assert _estoques(produto, variante, combo) == (10, 0, 4, 5)

    def test_estorno_depois_do_cancelado_nao_devolve_de_novo(self, pedido):
        ordem, produto, variante, combo = pedido
        servico = OrderService()
        servico.update_status(ordem, 'cancelled', notify_customer=False)

        servico.update_status(ordem, 'cancelled', notify_customer=False)
        servico.update_status(ordem, 'refunded', notify_customer=False)

        assert _estoques(produto, variante, combo) == (10, 0, 4, 5)

    def test_cancel_order_sem_restore_nao_mexe(self, pedido):
        ordem, produto, variante, combo = pedido

        OrderService().cancel_order(ordem, restore_stock=False)

        assert _estoques(produto, variante, combo) == (8, 2, 3, 4)
