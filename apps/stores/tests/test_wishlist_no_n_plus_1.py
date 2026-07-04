"""Performance (P1): a listagem da wishlist (storefront público) fazia
`products = [item.product for item in wishlist_items]` (1 query por item) e
depois serializava com StoreProductSerializer (category/product_type/variants
sem prefetch) → N+1 que escala com o tamanho da wishlist.

Este teste prova que a contagem de queries da resposta NÃO escala com o número
de produtos na wishlist.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreWishlist

User = get_user_model()


class WishlistNoNPlus1Test(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='wl-owner', email='ow@t.com', password='x')
        self.store = Store.objects.create(
            owner=self.owner, name='Loja WL', slug='loja-wl', status=Store.StoreStatus.ACTIVE,
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-wl', is_active=True, sort_order=1,
        )
        self.products = [
            StoreProduct.objects.create(
                store=self.store, category=self.category, name=f'P{i}', slug=f'p{i}-wl',
                price=Decimal('10.00'), status=StoreProduct.ProductStatus.ACTIVE,
            )
            for i in range(5)
        ]
        self.u_small = User.objects.create_user(username='wl-s', email='s@t.com', password='x')
        self.u_large = User.objects.create_user(username='wl-l', email='l@t.com', password='x')
        # Produtos DISJUNTOS: a constraint única é (store, customer_phone, product)
        # e o phone fica vazio, então produtos repetidos entre usuários colidiriam.
        self._add_wishlist('s@t.com', self.products[0:1])
        self._add_wishlist('l@t.com', self.products[1:5])
        self.url = f'/api/v1/stores/{self.store.slug}/wishlist/'

    def _add_wishlist(self, email, products):
        for p in products:
            StoreWishlist.objects.create(store=self.store, customer_email=email, product=p)

    def test_list_nao_escala_com_n_produtos(self):
        self.client.force_authenticate(self.u_small)
        with CaptureQueriesContext(connection) as q_small:
            r_s = self.client.get(self.url)
        self.assertEqual(r_s.status_code, 200, r_s.content)
        self.assertEqual(r_s.data['count'], 1)

        self.client.force_authenticate(self.u_large)
        with CaptureQueriesContext(connection) as q_large:
            r_l = self.client.get(self.url)
        self.assertEqual(r_l.status_code, 200, r_l.content)
        self.assertEqual(r_l.data['count'], 4)

        delta = len(q_large) - len(q_small)
        # 3 produtos extras. Com N+1 (product + category/variants por produto) o
        # delta seria ~6-9; com prefetch deve ficar em ~0 (folga de 2).
        self.assertLessEqual(
            delta, 2,
            f'N+1 na wishlist: +{delta} queries para 3 produtos extras '
            f'(pequeno={len(q_small)}, grande={len(q_large)})',
        )
