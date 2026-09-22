"""O carrinho guarda o contato assim que a pessoa digita.

Medido em 21/09 na Cê Saladas: 404 carrinhos em 30 dias, 108 com itens e TRÊS
com telefone. O telefone só era gravado quando o PEDIDO nascia — quem digitava
o número e desistia no meio do checkout sumia. São exatamente as pessoas que o
lembrete de carrinho existe para trazer de volta: já escolheram o que querem e
já se identificaram.

Guardar no carrinho não adiciona fricção nenhuma: é o mesmo dado, gravado mais
cedo.
"""
import pytest
from rest_framework.test import APIClient

from apps.stores.tests.factories import make_product, make_store


@pytest.fixture
def loja(db):
    return make_store()


def _cliente():
    c = APIClient()
    c.credentials(HTTP_X_CART_KEY='chave-de-teste-123')
    return c


def _carrinho_com_item(cliente, loja):
    produto = make_product(loja)
    r = cliente.post(f'/api/v1/stores/{loja.slug}/cart/add/', {
        'product_id': str(produto.id), 'quantity': 1,
    }, format='json')
    assert r.status_code in (200, 201), r.data
    return r


def test_guarda_o_telefone_no_carrinho(loja):
    cliente = _cliente()
    _carrinho_com_item(cliente, loja)

    r = cliente.post(f'/api/v1/stores/{loja.slug}/cart/contato/', {
        'telefone': '63 99261-8115', 'nome': 'Ana',
    }, format='json')

    assert r.status_code == 200
    from apps.stores.models.cart import StoreCart
    carrinho = StoreCart.objects.filter(store=loja).first()
    assert carrinho.metadata['customer_phone'] == '5563992618115'
    assert carrinho.metadata['customer_name'] == 'Ana'


def test_telefone_incompleto_nao_e_gravado(loja):
    """Metade de um número é pior que nada: o lembrete falharia calado."""
    cliente = _cliente()
    _carrinho_com_item(cliente, loja)

    r = cliente.post(f'/api/v1/stores/{loja.slug}/cart/contato/', {
        'telefone': '6399',
    }, format='json')

    assert r.status_code == 400
    from apps.stores.models.cart import StoreCart
    assert not (StoreCart.objects.filter(store=loja).first().metadata or {}).get('customer_phone')


def test_nome_sem_telefone_tambem_vale(loja):
    cliente = _cliente()
    _carrinho_com_item(cliente, loja)

    r = cliente.post(f'/api/v1/stores/{loja.slug}/cart/contato/', {'nome': 'Bia'}, format='json')

    assert r.status_code == 200
    from apps.stores.models.cart import StoreCart
    assert StoreCart.objects.filter(store=loja).first().metadata['customer_name'] == 'Bia'


def test_nao_apaga_o_resto_do_metadata(loja):
    from apps.stores.models.cart import StoreCart

    cliente = _cliente()
    _carrinho_com_item(cliente, loja)
    carrinho = StoreCart.objects.filter(store=loja).first()
    carrinho.metadata = {'cupom': 'SET10'}
    carrinho.save(update_fields=['metadata'])

    cliente.post(f'/api/v1/stores/{loja.slug}/cart/contato/', {
        'telefone': '63992618115',
    }, format='json')

    carrinho.refresh_from_db()
    assert carrinho.metadata['cupom'] == 'SET10'
    assert carrinho.metadata['customer_phone'] == '5563992618115'
