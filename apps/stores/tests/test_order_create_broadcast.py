"""POST /orders/ deve emitir order.created no WebSocket (30/jul).

Bug: StoreOrderViewSet.create() sobrescrito chamava serializer.save() direto
e nunca passava por perform_create() — o broadcast de order.created não
disparava e o painel só via pedido novo no refresh manual.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct

User = get_user_model()


class OrderCreateBroadcastTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='ownerws', email='ownerws@example.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Loja WS', slug='loja-ws', owner=self.owner, status='active'
        )
        self.product = StoreProduct.objects.create(
            store=self.store, name='Rondelli WS', slug='rondelli-ws',
            price=40, is_active=True, track_stock=False,
        )
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_create_order_broadcasts_order_created(self):
        with mock.patch(
            'apps.stores.api.views.order_views.broadcast_order_event'
        ) as broadcast, \
             mock.patch('celery.app.task.Task.apply_async'), \
             self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f'/api/v1/stores/{self.store.slug}/orders/',
                {
                    'customer_name': 'Cliente WS',
                    'customer_phone': '63999998888',
                    'payment_method': 'cash',
                    'delivery_method': 'pickup',
                    'items': [{'product_id': str(self.product.id), 'quantity': 1}],
                },
                format='json',
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        broadcast.assert_called_once()
        _, kwargs = broadcast.call_args
        self.assertEqual(kwargs.get('event_type'), 'order.created')
