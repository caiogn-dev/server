"""Foto da linha em "Meus pedidos" (24/11): variante e foto por link sumiam."""
from decimal import Decimal

import pytest

from apps.stores.api.webhooks import foto_do_item
from apps.stores.models import StoreOrder, StoreOrderItem
from apps.stores.tests.factories import make_product, make_store, make_variant


def _item(loja, produto, variante=None):
    pedido = StoreOrder.objects.create(
        store=loja, customer_name='Ana', subtotal=Decimal('10'), delivery_fee=Decimal('0'),
        total=Decimal('10'))
    return StoreOrderItem.objects.create(
        order=pedido, product=produto, variant=variante, product_name=produto.name,
        unit_price=Decimal('10'), quantity=1)


@pytest.mark.django_db
def test_variante_com_foto_propria():
    loja = make_store()
    produto = make_product(loja)
    v = make_variant(produto)
    v.image_url = 'https://cdn.exemplo.com/variante.jpg'
    v.save(update_fields=['image_url'])
    assert foto_do_item(_item(loja, produto, v)).endswith('/variante.jpg')


@pytest.mark.django_db
def test_variante_sem_foto_usa_a_do_produto_por_link():
    loja = make_store()
    produto = make_product(loja)
    produto.main_image_url = 'https://cdn.exemplo.com/produto.jpg'
    produto.save(update_fields=['main_image_url'])
    assert foto_do_item(_item(loja, produto, make_variant(produto))).endswith('/produto.jpg')


@pytest.mark.django_db
def test_produto_sem_variante_com_foto_por_link():
    loja = make_store()
    produto = make_product(loja)
    produto.main_image_url = 'https://cdn.exemplo.com/produto.jpg'
    produto.save(update_fields=['main_image_url'])
    assert foto_do_item(_item(loja, produto)).endswith('/produto.jpg')


@pytest.mark.django_db
def test_detalhe_por_token_traz_a_foto_da_variante():
    from rest_framework.test import APIClient
    loja = make_store()
    produto = make_product(loja)
    v = make_variant(produto)
    v.image_url = 'https://cdn.exemplo.com/variante.jpg'
    v.save(update_fields=['image_url'])
    item = _item(loja, produto, v)
    r = APIClient().get(f'/api/v1/stores/orders/by-token/{item.order.access_token}/')
    assert r.status_code == 200
    assert r.json()['items'][0]['image_url'].endswith('/variante.jpg')
