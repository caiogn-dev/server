"""Cancelar um pedido tem que liquidar o pagamento também.

O bug real: no balcão o pedido nasce `payment_status='paid'` (dinheiro na mão).
Quando o operador cancelava, só o `status` virava 'cancelled' — o `payment_status`
continuava 'paid' para sempre. Toda tela que somava `payment_status='paid'`
contava a venda desfeita como faturamento.

Em produção (05/ago/2026) isso inflava a loja `pastita` em R$ 631,79 sobre
R$ 2.812,01 reais — 22% de faturamento fantasma, todos pedidos de balcão
(cash/card). E o fechamento de caixa somava essa venda cancelada no total
esperado da gaveta.

Regra: ao cancelar, o pagamento vira 'refunded' se houve estorno de verdade,
senão 'cancelled'. Não existe mais pedido cancelado com pagamento 'paid' nem
'pending' pendurado.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder
from apps.stores.services.order_service import OrderService

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_cancel', password='x')
    return Store.objects.create(owner=dono, name='Loja Cancel', slug='loja-cancel-test')


def _pedido(loja, status='confirmed', pagamento='paid', metodo='cash', total='100.00'):
    return StoreOrder.objects.create(
        store=loja, total=Decimal(total), subtotal=Decimal(total),
        status=status, payment_status=pagamento, payment_method=metodo,
    )


@pytest.mark.django_db
class TestCancelamentoLiquidaPagamento:

    def test_cancel_order_de_venda_de_balcao_paga_zera_o_pagamento(self, loja):
        """O caso de produção: balcão em dinheiro, pago, cancelado."""
        pedido = _pedido(loja)

        OrderService().cancel_order(pedido, reason='cliente desistiu', restore_stock=False)

        pedido.refresh_from_db()
        assert pedido.status == 'cancelled'
        assert pedido.payment_status == 'cancelled'

    def test_update_status_para_cancelled_tambem_zera_o_pagamento(self, loja):
        """O painel cancela pelo dropdown de status, não pelo botão de cancelar."""
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'cancelled', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'cancelled'

    def test_pagamento_pendente_tambem_e_liquidado(self, loja):
        """Senão o cancelado continua contando em 'a receber' (revenue_pending)."""
        pedido = _pedido(loja, pagamento='pending', metodo='pix')

        OrderService().cancel_order(pedido, restore_stock=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'cancelled'

    def test_estorno_real_marca_refunded_e_nao_cancelled(self, loja):
        """Quem estornou de verdade precisa aparecer como estorno na conciliação."""
        pedido = _pedido(loja, metodo='pix')
        pedido.payment_id = 'MP-123'
        pedido.save(update_fields=['payment_id'])

        gateway = type('G', (), {'refund_payment': lambda self, pid: {'success': True}})()
        with patch('apps.stores.services.payment_service.get_payment_service', return_value=gateway):
            OrderService().cancel_order(pedido, refund=True, restore_stock=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'refunded'

    def test_pedido_ja_estornado_nao_e_sobrescrito(self, loja):
        pedido = _pedido(loja, status='cancelled', pagamento='refunded')
        pedido.status = 'confirmed'
        pedido.save(update_fields=['status'])

        OrderService().cancel_order(pedido, restore_stock=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'refunded'

    def test_pedido_entregue_normal_continua_pago(self, loja):
        """Guarda contra o fix vazar para o fluxo feliz."""
        pedido = _pedido(loja, status='out_for_delivery')

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'


@pytest.mark.django_db
class TestReceitaDepoisDoCancelamento:

    def test_venda_de_balcao_cancelada_sai_do_faturamento(self, loja):
        """Fim a fim: o que o painel soma depois do cancelamento."""
        from apps.stores.services.revenue import revenue_orders

        vendida = _pedido(loja, status='delivered', total='50.00')
        desfeita = _pedido(loja, total='100.00')
        OrderService().cancel_order(desfeita, restore_stock=False)

        pagos = StoreOrder.objects.filter(store=loja, payment_status='paid')
        assert list(pagos) == [vendida], 'cancelado ainda aparece como pago'
        assert revenue_orders(loja).count() == 1

    def test_fechamento_de_caixa_nao_espera_o_dinheiro_do_cancelado(self, loja):
        """A gaveta não tem o dinheiro da venda desfeita — o esperado não pode contar."""
        from apps.stores.models import StoreCashSession

        sessao = StoreCashSession.objects.create(
            store=loja, opening_amount=Decimal('0.00'), status='open',
        )
        _pedido(loja, status='delivered', total='50.00')
        desfeita = _pedido(loja, total='100.00')
        OrderService().cancel_order(desfeita, restore_stock=False)

        assert sessao.expected_cash() == Decimal('50.00')
