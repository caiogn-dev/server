"""Fase 3 — B1: amount_paid / amount_due derivados no StoreOrder + serializer.

amount_paid = soma dos StorePayment com status 'completed'.
amount_due  = max(0, total - amount_paid).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


def make_order(store, total='100.00'):
    return StoreOrder.objects.create(
        store=store,
        customer_name='Cliente',
        customer_phone='5599999999999',
        subtotal=Decimal(total),
        total=Decimal(total),
    )


class AmountPaidModelTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-amt', password='x')
        self.store = Store.objects.create(
            name='Loja Amt', slug='loja-amt', owner=self.owner, status='active',
        )

    def test_no_payments_zero_paid_full_due(self):
        order = make_order(self.store, '100.00')
        self.assertEqual(order.amount_paid, Decimal('0.00'))
        self.assertEqual(order.amount_due, Decimal('100.00'))
        self.assertFalse(order.is_fully_paid)

    def test_one_completed_partial(self):
        order = make_order(self.store, '100.00')
        StorePayment.objects.create(
            order=order, amount=Decimal('40.00'),
            payment_method='pix', status=StorePayment.PaymentStatus.COMPLETED,
        )
        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal('40.00'))
        self.assertEqual(order.amount_due, Decimal('60.00'))
        self.assertFalse(order.is_fully_paid)

    def test_pending_does_not_count(self):
        order = make_order(self.store, '100.00')
        StorePayment.objects.create(
            order=order, amount=Decimal('100.00'),
            payment_method='pix', status=StorePayment.PaymentStatus.PENDING,
        )
        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal('0.00'))
        self.assertEqual(order.amount_due, Decimal('100.00'))

    def test_sum_of_completed_fully_paid(self):
        order = make_order(self.store, '100.00')
        StorePayment.objects.create(
            order=order, amount=Decimal('60.00'),
            payment_method='pix', status=StorePayment.PaymentStatus.COMPLETED,
        )
        StorePayment.objects.create(
            order=order, amount=Decimal('40.00'),
            payment_method='pix', status=StorePayment.PaymentStatus.COMPLETED,
        )
        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal('100.00'))
        self.assertEqual(order.amount_due, Decimal('0.00'))
        self.assertTrue(order.is_fully_paid)

    def test_overpaid_due_floored_at_zero(self):
        order = make_order(self.store, '100.00')
        StorePayment.objects.create(
            order=order, amount=Decimal('120.00'),
            payment_method='pix', status=StorePayment.PaymentStatus.COMPLETED,
        )
        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal('120.00'))
        self.assertEqual(order.amount_due, Decimal('0.00'))
        self.assertTrue(order.is_fully_paid)


class AmountPaidSerializerTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-amt2', password='x')
        self.store = Store.objects.create(
            name='Loja Amt2', slug='loja-amt2', owner=self.owner, status='active',
        )
        self.client.force_authenticate(self.owner)

    def test_serializer_exposes_amount_fields(self):
        order = make_order(self.store, '100.00')
        StorePayment.objects.create(
            order=order, amount=Decimal('30.00'),
            payment_method='pix', status=StorePayment.PaymentStatus.COMPLETED,
        )
        url = f'/api/v1/stores/{self.store.slug}/orders/{order.id}/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(str(resp.data['amount_paid']), '30.00')
        self.assertEqual(str(resp.data['amount_due']), '70.00')
        self.assertFalse(resp.data['is_fully_paid'])
