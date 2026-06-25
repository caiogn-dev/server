"""Testes de recálculo de total e do endpoint POST /orders/{id}/adjust/."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()


def _make_product(store, price, name='Prod'):
    return StoreProduct.objects.create(
        store=store, name=name, slug=f'{name.lower()}-{price}',
        price=Decimal(price), track_stock=False, stock_quantity=0,
        status=StoreProduct.ProductStatus.ACTIVE,
    )


class RecalculateTotalsTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o1', email='o1@x.com', password='x')
        self.store = Store.objects.create(name='L1', slug='l1', owner=self.owner, status='active')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('0.00'), total=Decimal('0.00'),
        )
        self.p10 = _make_product(self.store, '10.00', 'P10')
        StoreOrderItem.objects.create(
            order=self.order, product=self.p10, product_name='P10', sku='',
            unit_price=Decimal('10.00'), quantity=2, subtotal=Decimal('20.00'),
        )

    def test_recalc_sums_items_into_subtotal_and_total(self):
        self.order.discount = Decimal('5.00')
        self.order.delivery_fee = Decimal('8.00')
        self.order.surcharge_value = Decimal('3.00')
        total = self.order.recalculate_totals()
        self.order.refresh_from_db()
        self.assertEqual(self.order.subtotal, Decimal('20.00'))
        # 20 - 5 + 0(tax) + 8 + 3 = 26
        self.assertEqual(self.order.total, Decimal('26.00'))
        self.assertEqual(total, Decimal('26.00'))

    def test_recalc_floors_total_at_zero(self):
        self.order.discount = Decimal('999.00')
        self.order.recalculate_totals()
        self.order.refresh_from_db()
        self.assertEqual(self.order.total, Decimal('0.00'))


class OrderReadFieldsTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o2', email='o2@x.com', password='x')
        self.store = Store.objects.create(name='L2', slug='l2', owner=self.owner, status='active')
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('20.00'), total=Decimal('23.00'),
            surcharge_value=Decimal('3.00'), surcharge_reason='taxa',
            manual_discount_reason='promo',
            manual_discount_value=Decimal('5.00'), manual_discount_type='fixed',
        )

    def test_read_exposes_surcharge_and_discount_reason(self):
        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Decimal(resp.data['surcharge_value']), Decimal('3.00'))
        self.assertEqual(resp.data['surcharge_reason'], 'taxa')
        self.assertEqual(resp.data['manual_discount_reason'], 'promo')
        self.assertEqual(Decimal(resp.data['manual_discount_value']), Decimal('5.00'))
        self.assertEqual(resp.data['manual_discount_type'], 'fixed')
