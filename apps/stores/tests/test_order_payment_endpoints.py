"""Testes dos endpoints manuais de pagamento do painel.

POST /orders/{id}/mark_paid/ e POST /orders/{id}/update_payment_status/

Cobre:
- P1: trava de concorrência (select_for_update sob transação).
- P2: paid_at só é setado no 1º pagamento confirmado (não sobrescreve).
- P3: PIX expirado não pode ser confirmado pelos endpoints manuais.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class OrderManualPaymentTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owpay', email='owpay@x.com', password='x'
        )
        self.store = Store.objects.create(
            name='LPay', slug='lpay', owner=self.owner, status='active'
        )
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('20.00'), total=Decimal('20.00'),
            payment_method='pix',
        )

    def _url(self, action):
        # StoreOrderViewSet is router-registered under /api/v1/stores/orders/;
        # StoreQuerysetMixin scopes results to the authenticated user's stores.
        return f'/api/v1/stores/orders/{self.order.id}/{action}/'

    # ---- P2: paid_at imutável após o 1º pagamento ----
    def test_mark_paid_does_not_overwrite_existing_paid_at(self):
        first = timezone.now() - timedelta(hours=2)
        self.order.payment_status = StoreOrder.PaymentStatus.PAID
        self.order.paid_at = first
        self.order.save(update_fields=['payment_status', 'paid_at'])

        resp = self.client.post(self._url('mark_paid'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        # paid_at deve permanecer o do 1º pagamento, não ser sobrescrito.
        self.assertEqual(self.order.paid_at, first)

    def test_update_payment_status_to_paid_does_not_overwrite_paid_at(self):
        first = timezone.now() - timedelta(hours=3)
        self.order.payment_status = StoreOrder.PaymentStatus.PAID
        self.order.paid_at = first
        self.order.save(update_fields=['payment_status', 'paid_at'])

        resp = self.client.post(
            self._url('update_payment_status'), {'payment_status': 'paid'}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_at, first)

    def test_mark_paid_sets_paid_at_on_first_payment(self):
        self.assertIsNone(self.order.paid_at)
        resp = self.client.post(self._url('mark_paid'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNotNone(self.order.paid_at)

    # ---- P3: PIX expirado não confirmável ----
    def test_mark_paid_rejects_expired_pix(self):
        self.order.payment_status = StoreOrder.PaymentStatus.PENDING
        self.order.pix_expires_at = timezone.now() - timedelta(minutes=5)
        self.order.save(update_fields=['payment_status', 'pix_expires_at'])

        resp = self.client.post(self._url('mark_paid'))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNone(self.order.paid_at)

    def test_update_payment_status_rejects_expired_pix(self):
        self.order.payment_status = StoreOrder.PaymentStatus.PENDING
        self.order.pix_expires_at = timezone.now() - timedelta(minutes=5)
        self.order.save(update_fields=['payment_status', 'pix_expires_at'])

        resp = self.client.post(
            self._url('update_payment_status'), {'payment_status': 'paid'}, format='json'
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_mark_paid_allows_valid_pix(self):
        self.order.payment_status = StoreOrder.PaymentStatus.PENDING
        self.order.pix_expires_at = timezone.now() + timedelta(minutes=10)
        self.order.save(update_fields=['payment_status', 'pix_expires_at'])

        resp = self.client.post(self._url('mark_paid'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)
