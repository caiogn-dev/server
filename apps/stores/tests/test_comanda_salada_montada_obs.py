"""Salada montada saía com "OBS: BASE: ALFACE | PROTEÍNA: ..." invertido (22/10).

O montador do cardápio grava o resumo dos ingredientes em `item.notes`, e a
comanda já lista os mesmos ingredientes nos detalhes — a cozinha via a salada
duas vezes e o "OBS" de verdade (pedido do cliente) se perdia no meio.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.services.print_service import build_order_print_payload

RESUMO = 'Base: Alface | Proteína: Frango em pedaços | Complementos: Mandioca, Mandioca, Milho | molhos: Mostarda e mel'
INGREDIENTES = [
    {'name': 'Alface', 'role': 'base', 'price': 0},
    {'name': 'Frango em pedaços', 'role': 'proteina', 'price': 0},
    {'name': 'Mandioca', 'role': 'complemento', 'price': 0},
    {'name': 'Milho', 'role': 'complemento', 'price': 0},
    {'name': 'Mostarda e mel', 'role': 'molho', 'price': 0},
]


@pytest.fixture
def pedido(db):
    dono = get_user_model().objects.create_user(
        username='dono-sal', email='dono-sal@teste.local', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Sal', slug='loja-sal', status='active')
    return StoreOrder.objects.create(
        store=loja, customer_name='C', customer_phone='5563900000009',
        subtotal=Decimal('45.00'), total=Decimal('45.00'),
    )


def _salada(pedido, notes):
    return StoreOrderItem.objects.create(
        order=pedido, product=None, product_name='Monte sua Salada', quantity=1,
        unit_price=Decimal('45.00'), subtotal=Decimal('45.00'), notes=notes,
        options={'type': 'custom_salad', 'ingredients': INGREDIENTES},
    )


def _item(pedido):
    return build_order_print_payload(pedido)['items'][0]


def test_resumo_do_montador_nao_vira_obs(pedido):
    _salada(pedido, RESUMO)
    item = _item(pedido)
    assert item['notes'] == ''
    assert any('Alface' in d for d in item['details'])


def test_pedido_do_cliente_continua_na_obs(pedido):
    _salada(pedido, f'{RESUMO} | Molho separado, por favor')
    assert _item(pedido)['notes'] == 'Molho separado, por favor'


def test_obs_so_do_cliente_fica_inteira(pedido):
    _salada(pedido, 'Sem cebola: alergia')
    assert _item(pedido)['notes'] == 'Sem cebola: alergia'


def test_item_comum_nao_mexe_na_obs(pedido):
    StoreOrderItem.objects.create(
        order=pedido, product=None, product_name='Queridinha', quantity=1,
        unit_price=Decimal('30.00'), subtotal=Decimal('30.00'),
        notes='Base: sem alface',
    )
    assert _item(pedido)['notes'] == 'Base: sem alface'
