"""Baixa de estoque na criação de pedido pela rota administrativa (PDV/dash).

O checkout do storefront já decrementa estoque (checkout_service); a rota
POST /stores/{slug}/orders/ usada pelo PDV não decrementava — pedido de
balcão bipado no scanner não dava baixa. Estes testes cobrem o gap.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct

User = get_user_model()


class PdvOrderStockDecrementTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='pdv1', email='pdv1@x.com', password='x')
        self.store = Store.objects.create(name='Balcao', slug='balcao', owner=self.owner, status='active')
        self.tracked = StoreProduct.objects.create(
            store=self.store, name='Marmita P', slug='marmita-p',
            price=Decimal('20.00'), track_stock=True, stock_quantity=10, sold_count=0,
            status=StoreProduct.ProductStatus.ACTIVE, barcode='2000042003501',
        )
        self.untracked = StoreProduct.objects.create(
            store=self.store, name='Suco', slug='suco',
            price=Decimal('8.00'), track_stock=False, stock_quantity=5, sold_count=0,
            status=StoreProduct.ProductStatus.ACTIVE,
        )
        self.client.force_authenticate(user=self.owner)

    def _create_order(self, items):
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/orders/',
            {
                'customer_name': 'Cliente Balcão',
                'customer_phone': '00000000000',
                'delivery_method': 'pickup',
                'payment_method': 'cash',
                'suppress_notifications': True,
                'items': items,
            },
            format='json',
        )

    def test_tracked_product_decrements_stock_and_increments_sold_count(self):
        resp = self._create_order([{'product_id': str(self.tracked.id), 'quantity': 3}])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.tracked.refresh_from_db()
        self.assertEqual(self.tracked.stock_quantity, 7)
        self.assertEqual(self.tracked.sold_count, 3)

    def test_untracked_product_stock_untouched(self):
        resp = self._create_order([{'product_id': str(self.untracked.id), 'quantity': 2}])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.untracked.refresh_from_db()
        self.assertEqual(self.untracked.stock_quantity, 5)
        self.assertEqual(self.untracked.sold_count, 0)

    def test_mixed_items_only_tracked_decrements(self):
        resp = self._create_order([
            {'product_id': str(self.tracked.id), 'quantity': 1},
            {'product_id': str(self.untracked.id), 'quantity': 4},
        ])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.tracked.refresh_from_db()
        self.untracked.refresh_from_db()
        self.assertEqual(self.tracked.stock_quantity, 9)
        self.assertEqual(self.untracked.stock_quantity, 5)
