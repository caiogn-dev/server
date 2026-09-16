"""Carimbo e cashback rodam juntos na mesma loja — o dono decide.

Até 16/set o painel tinha a trava "um programa OU outro": salvar um desligava
o outro. O dono queria os dois e via o programa "desativar de novo" ao
recarregar. A trava vivia só na tela; o backend sempre tratou os dois como
independentes. Este arquivo trava esse contrato do lado de cá, para ninguém
reintroduzir a exclusão aqui por engano.

Os dois juntos são seguros em dinheiro: no checkout o brinde do carimbo entra
primeiro e o cashback incide sobre o que sobrou (`subtotal - discount`), com
teto no próprio valor — o total nunca fica negativo.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.loyalty_service import LoyaltyService

TELEFONE = '5563999547790'


@pytest.fixture
def loja_com_os_dois(db):
    dono = get_user_model().objects.create_user(
        username='dono-2prog', email='dono-2prog@teste.local', password='x',
    )
    return Store.objects.create(
        owner=dono, name='Loja 2 Programas', slug='loja-2prog', store_type='food',
        status='active',
        metadata={'loyalty_enabled': True, 'cashback_enabled': True},
    )


@pytest.mark.django_db
class TestOsDoisProgramasLigados:
    def test_os_dois_constam_como_ligados(self, loja_com_os_dois):
        _, carimbo_ligado = LoyaltyService._config(loja_com_os_dois)
        assert carimbo_ligado is True
        assert CashbackService.is_enabled(loja_com_os_dois) is True

    def test_pedido_pago_gera_cashback_mesmo_com_carimbo_ligado(self, loja_com_os_dois):
        pedido = StoreOrder.objects.create(
            store=loja_com_os_dois, customer_name='Cliente', customer_phone=TELEFONE,
            subtotal=Decimal('50.00'), total=Decimal('50.00'), payment_status='paid',
        )
        CashbackService.credit_order(pedido)
        assert StoreCashbackLot.objects.filter(
            store=loja_com_os_dois, phone=TELEFONE,
        ).exists()

    def test_saldo_abate_com_carimbo_ligado_e_nunca_passa_do_que_sobrou(self, loja_com_os_dois):
        StoreCashbackLot.objects.create(
            store=loja_com_os_dois, phone=TELEFONE,
            amount=Decimal('100.00'), remaining=Decimal('100.00'),
            expires_at=timezone.now() + timedelta(days=30),
        )
        # 40 de pedido, 32 já abatidos pelo brinde do carimbo: sobram 8.
        sobra_depois_do_brinde = Decimal('8.00')
        assert CashbackService.aplicavel(
            loja_com_os_dois, TELEFONE, sobra_depois_do_brinde, verificado=True,
        ) == Decimal('8.00')
