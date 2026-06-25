"""A4 — views de delivery (Uber) sem auth/tenant check.

As views CreateDeliveryRequestView/DeliveryRequestStatusView/
CancelDeliveryRequestView não exigiam autenticação nem verificavam se o
usuário pertence à loja — qualquer um podia criar/cancelar entregas Uber
de pedidos alheios.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class DeliveryViewsAuthTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='downer', email='do@x.com', password='x')
        self.other = User.objects.create_user(username='dother', email='dt@x.com', password='x')
        self.store = Store.objects.create(name='DStore', slug='dstore', owner=self.owner, status='active')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('10.00'), total=Decimal('10.00'),
            status=StoreOrder.OrderStatus.CONFIRMED,
        )

    def _url(self):
        return f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/create-delivery-request/'

    def test_anonymous_is_rejected(self):
        resp = self.client.post(self._url())
        self.assertIn(resp.status_code, (401, 403), resp.content)

    def test_non_member_is_rejected(self):
        token = Token.objects.create(user=self.other)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_status_view_anonymous_rejected(self):
        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/delivery-request-status/'
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (401, 403), resp.content)

    def test_cancel_view_non_member_rejected(self):
        token = Token.objects.create(user=self.other)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/delivery-request/'
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 403, resp.content)
