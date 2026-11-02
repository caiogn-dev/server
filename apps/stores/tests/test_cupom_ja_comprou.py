"""Banner de boas-vindas some para quem já comprou (28/10).

O dono: o aviso do BEMVINDO10 tem que sumir para quem já comprou conosco ou
já usou o cupom. O cupom da Cê permitia 2 usos e não era só de primeira
compra — 33 de 62 usos foram de cliente antigo. O validate-coupon agora diz
`ja_comprou`, e o banner esconde o convite.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCoupon, StoreOrder

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_ja_comprou', password='x')
    loja = Store.objects.create(owner=dono, name='Loja JC', slug='loja-ja-comprou', status='active')
    StoreCoupon.objects.create(
        store=loja, code='BEMVINDO10', discount_type='percentage', discount_value=Decimal('10'),
        is_active=True, usage_limit_per_user=2,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=30),
    )
    return loja


def _pedido(loja, telefone, **extra):
    dados = dict(store=loja, customer_name='C', customer_phone=telefone, status='delivered',
                 payment_status='paid', subtotal=Decimal('40'), total=Decimal('40'))
    dados.update(extra)
    return StoreOrder.objects.create(**dados)


def _validar(loja, telefone):
    r = APIClient().post(f'/api/v1/stores/{loja.slug}/validate-coupon/',
                         {'code': 'BEMVINDO10', 'subtotal': 0, 'customer_phone': telefone}, format='json')
    assert r.status_code == 200, r.content
    return r.json()


def test_cliente_novo_nao_comprou(loja):
    assert _validar(loja, '63990000001')['ja_comprou'] is False


def test_quem_ja_comprou_sem_cupom_aparece_como_cliente(loja):
    _pedido(loja, '5563992289014')
    corpo = _validar(loja, '63992289014')
    assert corpo['valid'] is True
    assert corpo['ja_comprou'] is True


def test_quem_esgotou_o_cupom_tambem(loja):
    _pedido(loja, '5563984088587', coupon_code='BEMVINDO10')
    _pedido(loja, '5563984088587', coupon_code='BEMVINDO10')
    corpo = _validar(loja, '63984088587')
    assert corpo['valid'] is False
    assert corpo['ja_comprou'] is True


def test_pedido_cancelado_nao_conta(loja):
    _pedido(loja, '5563990000002', status='cancelled', payment_status='pending')
    assert _validar(loja, '63990000002')['ja_comprou'] is False
