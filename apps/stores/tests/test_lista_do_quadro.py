"""`?quadro=1`: só o que o quadro de pedidos mostra.

MEDIDO (nginx, 7 dias até 06/10): abrir a tela de Pedidos baixava os 500
pedidos mais recentes — ~570 KB comprimidos, 182 vezes, 85 MB — para exibir
o que está em aberto e os entregues de hoje. O resto era histórico que o
quadro jogava fora no navegador.

O quadro mostra: todo pedido em aberto, de qualquer dia (pedido parado de
ontem é o que mais precisa aparecer), e os entregues criados HOJE no fuso da
loja. Cancelado não aparece.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user('dono-quadro', 'q@t.com', 'x')
    return Store.objects.create(owner=dono, name='Loja Quadro', slug='loja-quadro', status='active')


def _pedido(loja, numero, status, dias_atras=0):
    p = StoreOrder.objects.create(
        store=loja, order_number=numero, status=status, total=Decimal('10'), subtotal=Decimal('10'),
        customer_name='C', customer_phone='5563999990000',
    )
    if dias_atras:
        StoreOrder.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=dias_atras))
    return p


def _lista(loja, **params):
    api = APIClient()
    api.force_authenticate(loja.owner)
    resp = api.get('/api/v1/stores/orders/', {'store': loja.slug, **params})
    assert resp.status_code == 200, resp.content
    return {o['order_number'] for o in resp.json()['results']}


@pytest.mark.django_db
def test_quadro_traz_abertos_de_qualquer_dia_e_entregues_de_hoje(loja):
    _pedido(loja, 'ABERTO-HOJE', 'pending')
    _pedido(loja, 'PREPARANDO-ONTEM', 'preparing', dias_atras=1)
    _pedido(loja, 'SAIU-3DIAS', 'out_for_delivery', dias_atras=3)
    _pedido(loja, 'ENTREGUE-HOJE', 'delivered')
    _pedido(loja, 'ENTREGUE-ONTEM', 'delivered', dias_atras=1)
    _pedido(loja, 'CONCLUIDO-ONTEM', 'completed', dias_atras=1)
    _pedido(loja, 'CANCELADO-HOJE', 'cancelled')

    assert _lista(loja, quadro=1) == {'ABERTO-HOJE', 'PREPARANDO-ONTEM', 'SAIU-3DIAS', 'ENTREGUE-HOJE'}


@pytest.mark.django_db
def test_sem_quadro_a_lista_continua_igual(loja):
    _pedido(loja, 'ENTREGUE-ONTEM', 'delivered', dias_atras=1)
    _pedido(loja, 'CANCELADO-HOJE', 'cancelled')
    assert _lista(loja) == {'ENTREGUE-ONTEM', 'CANCELADO-HOJE'}
