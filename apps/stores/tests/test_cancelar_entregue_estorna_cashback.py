"""Pedido entregue pode ser cancelado, e o cashback que ele gerou sai.

Dono (06/10): "estornar o cashback com certeza". Antes:
- o painel recusava cancelar pedido Entregue ("não pode ser cancelado");
- e NENHUM cancelamento tirava o cashback ganho no pedido — pago e depois
  cancelado, o cliente ficava com o bônus de uma compra que não existiu.

Contrato: cancelar (botão ou seletor de status) zera o que sobrou dos lotes de
compra/indicação daquele pedido. O que o cliente já gastou não vira dívida.
Pedido entregue cancelado não devolve estoque — a comida já saiu.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreCashbackLot, StoreOrder, StoreProduct
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.order_service import order_service

TELEFONE = '5563999542222'
INDICADOR = '5563999543333'


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-estorno', password='x')
    return Store.objects.create(
        owner=dono, name='Loja Estorno', slug='loja-estorno', store_type='food',
        status='active', metadata={'cashback_enabled': True, 'cashback_percent': 10},
    )


def _entregue(loja, **extra):
    dados = dict(
        store=loja, customer_name='Cliente', customer_phone=TELEFONE,
        subtotal=Decimal('100.00'), total=Decimal('100.00'), delivery_fee=Decimal('0'),
        payment_status='paid', status='delivered',
    )
    dados.update(extra)
    pedido = StoreOrder.objects.create(**dados)
    CashbackService.credit_purchase(pedido)
    return pedido


def _saldo():
    return sum(l.remaining for l in StoreCashbackLot.objects.filter(phone__endswith='999542222'))


@pytest.mark.django_db
class TestCancelarEntregue:
    def test_pedido_entregue_pode_ser_cancelado(self, loja):
        pedido = _entregue(loja)
        r = order_service.cancel_order(pedido, reason='cliente devolveu')
        assert r['success'], r
        pedido.refresh_from_db()
        assert pedido.status == 'cancelled'

    def test_cashback_da_compra_e_estornado(self, loja):
        pedido = _entregue(loja)
        assert _saldo() == Decimal('10.00')
        order_service.cancel_order(pedido, reason='cliente devolveu')
        assert _saldo() == Decimal('0.00')

    def test_cashback_ja_gasto_nao_vira_divida(self, loja):
        pedido = _entregue(loja)
        lote = StoreCashbackLot.objects.get(order=pedido)
        lote.remaining = Decimal('4.00')  # gastou 6 em outro pedido
        lote.save()
        order_service.cancel_order(pedido)
        lote.refresh_from_db()
        assert lote.remaining == Decimal('0.00')

    def test_indicacao_do_pedido_tambem_sai(self, loja):
        pedido = _entregue(loja)
        StoreCashbackLot.objects.create(
            store=loja, phone=INDICADOR, origin='referral', amount=Decimal('5'), remaining=Decimal('5'),
            order=pedido, expires_at=pedido.created_at.replace(year=2030),
        )
        order_service.cancel_order(pedido)
        assert StoreCashbackLot.objects.get(order=pedido, origin='referral').remaining == Decimal('0.00')

    def test_saldo_de_outros_pedidos_nao_e_tocado(self, loja):
        outro = _entregue(loja)
        pedido = _entregue(loja)
        order_service.cancel_order(pedido)
        assert StoreCashbackLot.objects.get(order=outro).remaining == Decimal('10.00')

    def test_entregue_cancelado_nao_devolve_estoque(self, loja):
        produto = StoreProduct.objects.create(
            store=loja, name='Marmita', slug='marmita', price=Decimal('100'), track_stock=True, stock_quantity=5,
        )
        pedido = _entregue(loja)
        pedido.items.create(product=produto, product_name='Marmita', quantity=1,
                            unit_price=Decimal('100'), subtotal=Decimal('100'))
        order_service.cancel_order(pedido)
        produto.refresh_from_db()
        assert produto.stock_quantity == 5

    def test_pelo_seletor_de_status_tambem_estorna(self, loja):
        pedido = _entregue(loja)
        r = order_service.update_status(pedido, 'cancelled')
        assert r['success'], r
        assert _saldo() == Decimal('0.00')

    def test_pago_cancelado_antes_de_entregar_tambem_estorna(self, loja):
        pedido = _entregue(loja, status='preparing')
        order_service.cancel_order(pedido)
        assert _saldo() == Decimal('0.00')
