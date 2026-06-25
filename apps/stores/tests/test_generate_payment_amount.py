"""Fase 3 — B3: generate_payment aceita amount + validações; create_link avulso."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


def _ok_payment(**over):
    base = {'success': True, 'payment_id': 'X', 'pix_code': 'PIX', 'amount': '50.00',
            'payment_db_id': 'db1', 'status': 'pending'}
    base.update(over)
    return base


class GeneratePaymentAmountTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-gp', password='x')
        self.store = Store.objects.create(
            name='Loja GP', slug='loja-gp', owner=self.owner, status='active',
        )
        self.client.force_authenticate(self.owner)

    def _order(self, total='100.00', paid='0.00', status='pending'):
        order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5599999999999',
            subtotal=Decimal(total), total=Decimal(total), status=status,
        )
        if Decimal(paid) > 0:
            StorePayment.objects.create(
                order=order, store=self.store, amount=Decimal(paid),
                payment_method='pix', status=StorePayment.PaymentStatus.COMPLETED,
            )
        return order

    def _url(self, order):
        return f'/api/v1/stores/{self.store.slug}/orders/{order.id}/generate_payment/'

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_default_amount_is_amount_due(self, mock_cp):
        mock_cp.return_value = _ok_payment()
        order = self._order('100.00', paid='30.00')  # amount_due = 70
        resp = self.client.post(self._url(order), {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        _, kwargs = mock_cp.call_args
        self.assertEqual(Decimal(str(kwargs['amount'])), Decimal('70.00'))

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_explicit_amount_passed(self, mock_cp):
        mock_cp.return_value = _ok_payment()
        order = self._order('100.00')
        resp = self.client.post(self._url(order), {'amount': '25.00'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        _, kwargs = mock_cp.call_args
        self.assertEqual(Decimal(str(kwargs['amount'])), Decimal('25.00'))

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_amount_zero_rejected(self, mock_cp):
        order = self._order('100.00')
        resp = self.client.post(self._url(order), {'amount': '0'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        mock_cp.assert_not_called()

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_negative_amount_rejected(self, mock_cp):
        order = self._order('100.00')
        resp = self.client.post(self._url(order), {'amount': '-5'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        mock_cp.assert_not_called()

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_fully_paid_no_amount_rejected(self, mock_cp):
        order = self._order('100.00', paid='100.00')  # amount_due = 0
        resp = self.client.post(self._url(order), {}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        mock_cp.assert_not_called()

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_cancelled_order_blocked(self, mock_cp):
        order = self._order('100.00', status='cancelled')
        resp = self.client.post(self._url(order), {'amount': '10'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        mock_cp.assert_not_called()

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_refunded_order_blocked(self, mock_cp):
        order = self._order('100.00', status='refunded')
        resp = self.client.post(self._url(order), {'amount': '10'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        mock_cp.assert_not_called()


class CreateLinkAvulsoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-cl', password='x')
        self.store = Store.objects.create(
            name='Loja CL', slug='loja-cl', owner=self.owner, status='active',
        )
        self.other = User.objects.create_user(username='o-other', password='x')
        self.other_store = Store.objects.create(
            name='Outra', slug='outra', owner=self.other, status='active',
        )
        self.client.force_authenticate(self.owner)
        self.url = '/api/v1/stores/payments/create_link/'

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_create_link_calls_service_avulso(self, mock_cp):
        mock_cp.return_value = _ok_payment(amount='40.00')
        resp = self.client.post(self.url, {
            'store': str(self.store.id), 'amount': '40.00', 'description': 'Cobrança X',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        args, kwargs = mock_cp.call_args
        # order deve ser None (avulso) e store/amount/description repassados
        self.assertIsNone(args[0] if args else kwargs.get('order'))
        self.assertEqual(kwargs['store'].id, self.store.id)
        self.assertEqual(Decimal(str(kwargs['amount'])), Decimal('40.00'))

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_create_link_amount_zero_rejected(self, mock_cp):
        resp = self.client.post(self.url, {
            'store': str(self.store.id), 'amount': '0',
        }, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        mock_cp.assert_not_called()

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_create_link_foreign_store_forbidden(self, mock_cp):
        resp = self.client.post(self.url, {
            'store': str(self.other_store.id), 'amount': '40.00',
        }, format='json')
        self.assertIn(resp.status_code, (403, 404), resp.content)
        mock_cp.assert_not_called()
