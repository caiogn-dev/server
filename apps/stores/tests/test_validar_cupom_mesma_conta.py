"""A validação do cupom na sacola faz a MESMA conta do checkout (26/10).

`/validate-coupon/` tinha a sua cópia do cálculo: percentual sem olhar o
escopo do cupom, fixo sem limite ao subtotal. O cardápio mostrava esse
desconto e o checkout (`StoreCoupon.calculate_discount`) cobrava outro.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreCoupon, StoreProduct,
)

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_cupom_conta', password='x')
    return Store.objects.create(owner=dono, name='Loja Cupom', slug='loja-cupom-conta', status='active')


def _cupom(loja, **extra):
    dados = dict(
        store=loja, code='TESTE', discount_type='percentage', discount_value=Decimal('50'),
        is_active=True,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=1),
    )
    dados.update(extra)
    return StoreCoupon.objects.create(**dados)


def _validar(loja, subtotal, cart_key=None):
    cliente = APIClient()
    if cart_key:
        cliente.credentials(HTTP_X_CART_KEY=cart_key)
    url = reverse('stores:store-validate-coupon', kwargs={'store_slug': loja.slug})
    return cliente.post(url, {'code': 'teste', 'subtotal': str(subtotal)}, format='json').json()


def test_fixo_maior_que_o_subtotal_vale_o_subtotal(loja):
    _cupom(loja, discount_type='fixed', discount_value=Decimal('30'))
    assert Decimal(_validar(loja, 20)['coupon']['calculated_discount']) == Decimal('20')


def test_teto_do_percentual_vale(loja):
    _cupom(loja, max_discount=Decimal('10'))
    assert Decimal(_validar(loja, 100)['coupon']['calculated_discount']) == Decimal('10')


def test_cupom_de_categoria_desconta_so_a_categoria(loja):
    saladas = StoreCategory.objects.create(store=loja, name='Saladas', slug='saladas')
    bebidas = StoreCategory.objects.create(store=loja, name='Bebidas', slug='bebidas')
    salada = StoreProduct.objects.create(store=loja, category=saladas, name='Salada', slug='salada',
                                         price=Decimal('40'), status='active', track_stock=False)
    suco = StoreProduct.objects.create(store=loja, category=bebidas, name='Suco', slug='suco',
                                       price=Decimal('10'), status='active', track_stock=False)
    cart = StoreCart.objects.create(store=loja, session_key='sess-cupom-conta')
    StoreCartItem.objects.create(cart=cart, product=salada, quantity=1)
    StoreCartItem.objects.create(cart=cart, product=suco, quantity=1)
    _cupom(loja, applicable_categories=[str(saladas.id)])

    resposta = _validar(loja, 50, cart_key='sess-cupom-conta')

    # 50% da salada (R$ 40), não dos R$ 50 da sacola.
    assert Decimal(resposta['coupon']['calculated_discount']) == Decimal('20')


def test_cupom_invalido_continua_dizendo_o_motivo(loja):
    _cupom(loja, min_purchase=Decimal('80'))
    resposta = _validar(loja, 50)
    assert resposta['valid'] is False
    assert 'mínimo' in resposta['error']
