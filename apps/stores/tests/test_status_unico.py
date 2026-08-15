"""Mudar status é UMA implementação, e ela sabe da regra do dinheiro.

Medido em produção em 14/08: 28 pedidos em dinheiro entregues, 26 pagos, 2 não.
R$ 306,00 entregues em mãos e fora do faturamento (CE-2607316642, R$ 95,00, e
KER2608076764, R$ 211,00).

A causa: `OrderService.update_status` — o caminho do PAINEL — reescreve toda a
lógica de timestamps, chama `order.save()` e nunca chama
`StoreOrder.update_status`, que é onde mora "dinheiro entregue vira pago". Ele
trata `cancelled` como caso especial e não trata `delivered`.

Duas implementações da mesma decisão sempre divergem. Esta diverge em dinheiro.
"""
from decimal import Decimal

import pytest

from apps.stores.models import StoreOrder
from apps.stores.services.order_service import OrderService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _pedido(loja, metodo='cash', status='out_for_delivery'):
    return StoreOrder.objects.create(
        store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
        status=status, payment_status='pending', payment_method=metodo,
        customer_phone='+5563984143551', customer_name='gabriela',
    )


@pytest.mark.django_db
class TestDinheiroEntregueViraReceita:
    def test_o_caminho_do_painel_marca_pago(self, loja):
        """O bug dos R$ 306: entregar pelo painel não liquidava a venda."""
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'

    def test_e_carimba_quando_foi_pago(self, loja):
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.paid_at is not None

    def test_concluir_tambem_liquida(self, loja):
        pedido = _pedido(loja, status='delivered')

        OrderService().update_status(pedido, 'completed', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'


@pytest.mark.django_db
class TestOQueNaoPodeMudar:
    def test_pix_entregue_NAO_e_marcado_pago(self, loja):
        """Online paga por webhook ANTES de entregar. Marcar aqui inventaria
        receita de um PIX que o cliente nunca pagou."""
        pedido = _pedido(loja, metodo='pix')

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'pending'

    def test_transicao_invalida_continua_recusada(self, loja):
        pedido = _pedido(loja, status='pending')

        r = OrderService().update_status(pedido, 'delivered', notify_customer=False)

        assert r['success'] is False
        pedido.refresh_from_db()
        assert pedido.status == 'pending'

    def test_o_timestamp_de_entrega_continua_preenchido(self, loja):
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.delivered_at is not None

    def test_a_nota_continua_sendo_anexada(self, loja):
        pedido = _pedido(loja)

        OrderService().update_status(
            pedido, 'delivered', notify_customer=False, notes='deixado na portaria',
        )

        pedido.refresh_from_db()
        assert 'portaria' in pedido.notes

    def test_cancelar_continua_liquidando_o_pagamento(self, loja):
        """Regressão: o dropdown do painel cancela por aqui."""
        pedido = _pedido(loja, status='pending')

        r = OrderService().update_status(pedido, 'cancelled', notify_customer=False)

        assert r['success'] is True
        pedido.refresh_from_db()
        assert pedido.status == 'cancelled'
