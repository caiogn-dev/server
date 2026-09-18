"""Cancelar o pedido não devolve o saldo que o cliente usou para pagá-lo.

`OrderService._encerrar_cancelado` é o que todo cancelamento faz, venha do
botão ou do dropdown do painel. Ele liquida o `payment_status` e devolve a
vaga do cupom — e só. O saldo que o cliente gastou no pedido
(`CashbackService.redeem`, que baixa os lotes e grava um
`StoreCashbackRedemption`) fica gasto.

Para o cashback de compra são centavos. Para a CARTEIRA PRÉ-PAGA é dinheiro
que o cliente pagou antes, via PIX, e que a loja agora retém por um pedido que
ela mesma cancelou. O cliente abre a carteira e o saldo diminuiu sem ele ter
comido nada.

A devolução é `CashbackService.devolver_resgate`, chamada por
`_encerrar_cancelado`: um lote novo com a validade mais longa da loja,
idempotente por `source_ref='estorno:<pedido>'`.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.order_service import order_service

TELEFONE = '5563999541111'


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(
        username='dono-devolve', email='dono-devolve@teste.local', password='x',
    )
    return Store.objects.create(
        owner=dono, name='Loja Devolve', slug='loja-devolve', store_type='food',
        status='active', metadata={'cashback_enabled': True},
    )


def _pedido_pago_com_saldo(loja, saldo='50.00', usado='30.00'):
    StoreCashbackLot.objects.create(
        store=loja, phone=TELEFONE, amount=Decimal(saldo), remaining=Decimal(saldo),
        expires_at=timezone.now() + timedelta(days=60),
    )
    pedido = StoreOrder.objects.create(
        store=loja, customer_name='Cliente', customer_phone=TELEFONE,
        subtotal=Decimal('40.00'), total=Decimal('10.00'), payment_status='paid',
    )
    abatido = CashbackService.redeem(loja, TELEFONE, pedido, Decimal(usado), verificado=True)
    assert abatido == Decimal(usado)
    return pedido


@pytest.mark.django_db
class TestCancelarDevolveOSaldo:
    def test_saldo_volta_depois_de_cancelar(self, loja):
        pedido = _pedido_pago_com_saldo(loja)
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('20.00')

        order_service.cancel_order(pedido, reason='loja sem ingrediente')

        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('50.00')

    def test_cancelar_duas_vezes_nao_devolve_em_dobro(self, loja):
        """Idempotência: o segundo cancelamento não pode imprimir saldo."""
        pedido = _pedido_pago_com_saldo(loja)

        order_service.cancel_order(pedido, reason='1ª')
        pedido.refresh_from_db()
        order_service.update_status(pedido, 'cancelled')

        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('50.00')
