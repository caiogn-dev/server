"""products_count de StoreProductType não pode gerar 1 query por linha."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct
from apps.stores.models.product import StoreProductType

User = get_user_model()


class ProductTypeQueryCountTest(APITestCase):
    _seq = 0

    def _setup(self, n):
        ProductTypeQueryCountTest._seq += 1
        k = ProductTypeQueryCountTest._seq
        self.owner = User.objects.create_user(username=f'o{k}', password='x')
        self.store = Store.objects.create(name='L', slug=f'l{k}', owner=self.owner, status='active')
        self.types = []
        for i in range(n):
            t = StoreProductType.objects.create(store=self.store, name=f'T{i}', slug=f't{i}')
            for j in range(2):
                StoreProduct.objects.create(store=self.store, name=f'P{i}{j}', slug=f'p{i}-{j}', price=Decimal('10'),
                                            product_type=t, status='active')
            StoreProduct.objects.create(store=self.store, name=f'X{i}', slug=f'x{i}', price=Decimal('10'),
                                        product_type=t, status='draft')
        self.client.force_authenticate(self.owner)

    def _count(self, url):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        rows = data['results'] if isinstance(data, dict) else data
        return len(ctx), rows

    def test_listagem_constante_e_contagem_correta(self):
        for url in ('/api/v1/stores/product-types/', '/api/v1/stores/admin/product-types/'):
            with self.subTest(url=url):
                StoreProductType.objects.all().delete()
                Store.objects.all().delete()
                self._setup(2)
                q2, rows = self._count(url + f'?store={self.store.id}')
                self.assertTrue(all(r['products_count'] == 2 for r in rows))
                Store.objects.all().delete()
                StoreProductType.objects.all().delete()
                self._setup(6)
                q6, rows = self._count(url + f'?store={self.store.id}')
                self.assertEqual(len(rows), 6)
                self.assertTrue(all(r['products_count'] == 2 for r in rows))
                self.assertEqual(q2, q6)
