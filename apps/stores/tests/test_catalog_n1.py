"""Regressão N+1 nos endpoints de catálogo do painel (produtos e categorias).

Produtos: StoreProductSerializer serializa `variants` (reverse FK) sempre, mas o
branch de LIST do get_queryset não tinha prefetch → 1 query de variants por produto.
Categorias: get_products_count fazia products.count() por categoria + get_children
recursivo → N+1 em store_products/store_categories.

Prova O(1) com 2 pontos de dados: dobrar as linhas NÃO pode aumentar as queries.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models import StoreProduct, StoreCategory, StoreProductVariant

User = get_user_model()


class CatalogListNoN1Test(APITestCase):
    def _store(self, slug, n_products, n_cats):
        owner = User.objects.create_user(username=f'o-{slug}', email=f'o-{slug}@t.com', password='x')
        store = Store.objects.create(name=slug, slug=slug, owner=owner, status='active')
        cats = [StoreCategory.objects.create(store=store, name=f'Cat{i}', slug=f'{slug}-cat{i}')
                for i in range(n_cats)]
        for i in range(n_products):
            p = StoreProduct.objects.create(
                store=store, category=cats[i % n_cats], name=f'P{i}', slug=f'{slug}-p{i}',
                price=Decimal('10.00'), status=StoreProduct.ProductStatus.ACTIVE,
            )
            # 2 variantes por produto: a N+1 dispararia 1 query/produto aqui.
            StoreProductVariant.objects.create(product=p, name='P', price=Decimal('10.00'))
            StoreProductVariant.objects.create(product=p, name='G', price=Decimal('12.00'))
        return owner, store

    def _q(self, owner, url):
        self.client.force_authenticate(owner)
        self.client.get(url)  # warmup
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        return len(ctx.captured_queries)

    def test_products_list_is_o1(self):
        o4, s4 = self._store('cat-p4', 4, 2)
        o12, s12 = self._store('cat-p12', 12, 2)
        q4 = self._q(o4, f'/api/v1/stores/products/?store={s4.slug}&page_size=100')
        q12 = self._q(o12, f'/api/v1/stores/products/?store={s12.slug}&page_size=100')
        self.assertEqual(q4, q12, f'N+1 em produtos: 4={q4} vs 12={q12} queries')

    def test_categories_list_is_o1(self):
        o2, s2 = self._store('cat-c2', 2, 2)
        o6, s6 = self._store('cat-c6', 6, 6)
        q2 = self._q(o2, f'/api/v1/stores/categories/?store={s2.slug}')
        q6 = self._q(o6, f'/api/v1/stores/categories/?store={s6.slug}')
        self.assertEqual(q2, q6, f'N+1 em categorias: 2={q2} vs 6={q6} queries')
