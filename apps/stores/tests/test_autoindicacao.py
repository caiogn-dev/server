"""Quem indica a si mesmo não ganha crédito de indicação — nem com telefone estrangeiro.

Produção, 15/set: a Layane (Espanha, 34647520824) abriu o próprio link de
indicação, que chegou como `indicado_por=5534647520824` (um "55" grudado na
frente). A trava de auto-indicação comparava `normalize_phone_number` dos
dois — 5534647520824 × 34647520824 — e creditou R$ 3,76 de "indicação" para
um número brasileiro que não existe.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService
from apps.stores.tests.factories import make_store

User = get_user_model()


@pytest.fixture
def loja(db, monkeypatch):
    loja = make_store(name='Cê Indica', city='Palmas', state='TO')
    monkeypatch.setattr(CashbackService, 'is_enabled', staticmethod(lambda store: True))
    return loja


def _pedido(loja, telefone):
    return StoreOrder.objects.create(
        store=loja, total=Decimal('80'), subtotal=Decimal('80'), payment_status='paid',
        customer_phone=telefone,
    )


@pytest.mark.django_db
@pytest.mark.parametrize('cliente, indicador', [
    ('34647520824', '5534647520824'),     # o caso da Layane
    ('34647520824', '+34647520824'),
    ('5563992338269', '556392338269'),    # nono dígito
    ('5563992338269', '63992338269'),
])
def test_mesma_pessoa_nao_credita(loja, cliente, indicador):
    pedido = _pedido(loja, cliente)

    assert CashbackService.credit_referral(pedido, None, owner_phone=indicador) is None
    assert not StoreCashbackLot.objects.filter(origin=StoreCashbackLot.Origin.REFERRAL).exists()


@pytest.mark.django_db
def test_outra_pessoa_credita(loja):
    pedido = _pedido(loja, '5563992338269')

    lote = CashbackService.credit_referral(pedido, None, owner_phone='5563984289103')

    assert lote is not None
