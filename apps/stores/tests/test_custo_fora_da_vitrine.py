"""
Preço de custo NÃO sai em rota pública.

O catálogo da vitrine (`/stores/{slug}/catalog/`) e a lista de favoritos são
AllowAny e reaproveitavam o `StoreProductSerializer` do painel, que inclui
`cost_price`. Em 03/10/2026, 7 dos 36 produtos da Cê Saladas tinham o custo
visível para qualquer um que chamasse a API — o storefront até removia o
campo do HTML, mas a API seguia aberta.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.stores.models import StoreWishlist
from apps.stores.tests.factories import make_product, make_store


def _todos_os_produtos(payload):
    yield from payload.get('products', [])
    yield from payload.get('featured_products', [])
    for bloco in payload.get('products_by_category', []):
        yield from bloco.get('products', [])


class CustoForaDaVitrineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store = make_store()
        cls.produto = make_product(cls.store, price=Decimal('23.00'))
        cls.produto.cost_price = Decimal('9.40')
        cls.produto.featured = True
        cls.produto.save(update_fields=['cost_price', 'featured'])

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_catalogo_publico_nao_tem_custo(self):
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/catalog/')
        assert r.status_code == 200
        produtos = list(_todos_os_produtos(r.json()))
        assert produtos, 'o catálogo devia trazer o produto'
        assert all('cost_price' not in p for p in produtos), produtos[0].keys()
        # O resto do contrato da vitrine continua lá.
        assert produtos[0]['price'] == '23.00'

    def test_favoritos_publicos_nao_tem_custo(self):
        user = get_user_model().objects.create_user(username='cli', email='cli@x.com', password='pw')
        StoreWishlist.objects.create(store=self.store, customer_email='cli@x.com', product=self.produto)
        self.client.force_authenticate(user)
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/wishlist/')
        assert r.status_code == 200
        produtos = r.json()['products']
        assert len(produtos) == 1
        assert 'cost_price' not in produtos[0]
