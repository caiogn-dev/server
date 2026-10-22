"""Quem lançou o pedido no painel/PDV (22/10).

O ranking "Atendentes" de Equipe e entregas lê `created_by_staff`, mas
ninguém gravava o campo: a Cê lançou 51 pedidos no PDV em 30 dias e o quadro
dizia "Nenhum pedido lançado no painel".
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from apps.stores.api.serializers import StoreOrderCreateSerializer
from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê')


@pytest.fixture
def produto(loja):
    return StoreProduct.objects.create(
        store=loja, name='Salada', price='30.00',
        status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
    )


def criar(loja, produto, user=None):
    request = APIRequestFactory().post('/')
    request.user = user
    dados = {
        'store': loja.slug, 'customer_name': 'Cliente', 'customer_phone': '63999990000',
        'delivery_method': 'pickup', 'source': 'pdv',
        'items': [{'product_id': str(produto.id), 'quantity': 1}],
    }
    s = StoreOrderCreateSerializer(data=dados, context={'request': request} if user else {})
    assert s.is_valid(), s.errors
    return s.save()


@pytest.mark.django_db
def test_pedido_lancado_no_painel_fica_com_quem_lancou(loja, produto):
    pedido = criar(loja, produto, user=loja.owner)
    assert pedido.created_by_staff_id == loja.owner.id


@pytest.mark.django_db
def test_sem_usuario_logado_fica_sem_atendente(loja, produto):
    assert criar(loja, produto).created_by_staff_id is None


@pytest.mark.django_db
def test_anonimo_nao_vira_atendente(loja, produto):
    from django.contrib.auth.models import AnonymousUser
    assert criar(loja, produto, user=AnonymousUser()).created_by_staff_id is None
