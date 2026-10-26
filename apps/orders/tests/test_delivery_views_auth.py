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


class UberSoComLojaLigadaTestCase(APITestCase):
    """26/10: as credenciais do Uber são da PLATAFORMA (env), não da loja.
    Qualquer operador de qualquer loja pedia corrida cobrada na conta da
    plataforma — o botão aparecia em todo pedido de entrega e nunca foi usado
    (583 pedidos, 0 com Uber). Só pede quem tem `metadata.uber_direct`."""

    def setUp(self):
        from unittest import mock
        self.owner = User.objects.create_user(username='uowner', email='uo@x.com', password='x')
        self.store = Store.objects.create(name='UStore', slug='ustore', owner=self.owner, status='active')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('10.00'), total=Decimal('10.00'),
            status=StoreOrder.OrderStatus.CONFIRMED,
        )
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        patcher = mock.patch('apps.orders.views.create_uber_delivery_request')
        self.task = patcher.start()
        self.addCleanup(patcher.stop)

    def _url(self):
        return f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/create-delivery-request/'

    def test_loja_sem_uber_ligado_nao_pede_corrida(self):
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 403, resp.content)
        self.task.delay.assert_not_called()

    def test_loja_com_uber_ligado_pede(self):
        self.store.metadata = {'uber_direct': True}
        self.store.save(update_fields=['metadata'])
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 202, resp.content)
        self.task.delay.assert_called_once()
