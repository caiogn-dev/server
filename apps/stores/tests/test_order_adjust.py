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


class OrderAdjustMoneyTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o3', email='o3@x.com', password='x')
        self.store = Store.objects.create(name='L3', slug='l3', owner=self.owner, status='active')
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('20.00'), total=Decimal('20.00'),
        )
        self.p = _make_product(self.store, '10.00', 'P10')
        StoreOrderItem.objects.create(
            order=self.order, product=self.p, product_name='P10', sku='',
            unit_price=Decimal('10.00'), quantity=2, subtotal=Decimal('20.00'),
        )
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/adjust/'

    def test_apply_discount_surcharge_delivery_recalculates_total(self):
        resp = self.client.post(self.url, {
            'discount': '5.00', 'discount_reason': 'fiel',
            'surcharge_value': '3.00', 'surcharge_reason': 'embalagem',
            'delivery_fee': '8.00',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.discount, Decimal('5.00'))
        self.assertEqual(self.order.manual_discount_reason, 'fiel')
        self.assertEqual(self.order.surcharge_value, Decimal('3.00'))
        self.assertEqual(self.order.surcharge_reason, 'embalagem')
        self.assertEqual(self.order.delivery_fee, Decimal('8.00'))
        # 20 - 5 + 8 + 3 = 26
        self.assertEqual(self.order.total, Decimal('26.00'))

    def test_discount_bigger_than_subtotal_is_rejected(self):
        resp = self.client.post(self.url, {'discount': '999.00'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total, Decimal('20.00'))  # inalterado

    def test_cannot_adjust_cancelled_order(self):
        self.order.status = StoreOrder.OrderStatus.CANCELLED
        self.order.save(update_fields=['status'])
        resp = self.client.post(self.url, {'discount': '1.00'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_requires_authentication(self):
        self.client.credentials()  # remove token
        resp = self.client.post(self.url, {'discount': '1.00'}, format='json')
        self.assertIn(resp.status_code, (401, 403))


class OrderAdjustItemsTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o4', email='o4@x.com', password='x')
        self.store = Store.objects.create(name='L4', slug='l4', owner=self.owner, status='active')
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('10.00'), total=Decimal('10.00'),
        )
        self.p10 = _make_product(self.store, '10.00', 'P10')
        self.p25 = _make_product(self.store, '25.00', 'P25')
        self.item = StoreOrderItem.objects.create(
            order=self.order, product=self.p10, product_name='P10', sku='',
            unit_price=Decimal('10.00'), quantity=1, subtotal=Decimal('10.00'),
        )
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/adjust/'

    def test_add_item_recomputes_subtotal_and_total(self):
        resp = self.client.post(self.url, {
            'item_ops': [{'op': 'add', 'product_id': str(self.p25.id), 'quantity': 2}],
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        # 10 (existente) + 25*2 = 60
        self.assertEqual(self.order.subtotal, Decimal('60.00'))
        self.assertEqual(self.order.total, Decimal('60.00'))
        self.assertEqual(self.order.items.count(), 2)

    def test_update_item_quantity(self):
        resp = self.client.post(self.url, {
            'item_ops': [{'op': 'update', 'item_id': str(self.item.id), 'quantity': 3}],
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        self.assertEqual(self.item.subtotal, Decimal('30.00'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.total, Decimal('30.00'))

    def test_remove_item(self):
        extra = StoreOrderItem.objects.create(
            order=self.order, product=self.p25, product_name='P25', sku='',
            unit_price=Decimal('25.00'), quantity=1, subtotal=Decimal('25.00'),
        )
        resp = self.client.post(self.url, {
            'item_ops': [{'op': 'remove', 'item_id': str(extra.id)}],
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.items.count(), 1)
        self.assertEqual(self.order.total, Decimal('10.00'))

    def test_cannot_remove_last_item(self):
        resp = self.client.post(self.url, {
            'item_ops': [{'op': 'remove', 'item_id': str(self.item.id)}],
        }, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.items.count(), 1)

    def test_add_unknown_product_rejected(self):
        import uuid
        resp = self.client.post(self.url, {
            'item_ops': [{'op': 'add', 'product_id': str(uuid.uuid4()), 'quantity': 1}],
        }, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_update_item_from_another_order_rejected(self):
        other = StoreOrder.objects.create(
            store=self.store, customer_name='X', customer_phone='6311112222',
            subtotal=Decimal('10.00'), total=Decimal('10.00'),
        )
        alien = StoreOrderItem.objects.create(
            order=other, product=self.p10, product_name='P10', sku='',
            unit_price=Decimal('10.00'), quantity=1, subtotal=Decimal('10.00'),
        )
        resp = self.client.post(self.url, {
            'item_ops': [{'op': 'update', 'item_id': str(alien.id), 'quantity': 2}],
        }, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_failed_op_rolls_back_earlier_ops(self):
        """Um add válido seguido de um op inválido NÃO pode persistir o add
        (rollback do atomic via raise, não return)."""
        import uuid
        resp = self.client.post(self.url, {
            'item_ops': [
                {'op': 'add', 'product_id': str(self.p25.id), 'quantity': 1},
                {'op': 'remove', 'item_id': str(uuid.uuid4())},  # falha → rollback
            ],
        }, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.items.count(), 1)  # add desfeito
        self.assertEqual(self.order.total, Decimal('10.00'))  # total intacto
