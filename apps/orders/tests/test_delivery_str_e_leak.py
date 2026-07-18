"""Regressão de segurança: handlers de exceção nas views de delivery Uber
não devem expor str(e) nas respostas HTTP.

Vetor: `except Exception as e: return Response({'detail': str(e)}, 500)`
vaza mensagens internas da Uber API (incluindo tokens, endpoints, dados de
rastreamento) e do ORM para qualquer usuário autenticado que acione uma
falha de rede/API.

Três views afetadas: CreateDeliveryRequestView, DeliveryRequestStatusView,
CancelDeliveryRequestView.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.orders.views import (
    CancelDeliveryRequestView,
    CreateDeliveryRequestView,
    DeliveryRequestStatusView,
)

_SECRET = 'Uber internal: host=prod-api.uber.com token=bearer-SUPERSECRET trace=abc123'


def _mock_store():
    s = MagicMock()
    s.id = 'store-uuid-111'
    s.slug = 'loja-test'
    return s


def _mock_order_create():
    o = MagicMock()
    o.id = 'order-uuid-222'
    o.status = 'confirmed'
    o.uber_delivery_request_id = None
    return o


def _mock_order_with_request():
    o = MagicMock()
    o.id = 'order-uuid-222'
    o.status = 'confirmed'
    o.uber_delivery_request_id = 'req-uber-999'
    return o


class CreateDeliveryStrELeakTest(SimpleTestCase):
    """create-delivery-request não expõe str(e) em HTTP 500."""

    def setUp(self):
        self.factory = APIRequestFactory()

    @patch('apps.orders.views.create_uber_delivery_request')
    @patch('apps.orders.views.get_object_or_404', return_value=_mock_order_create())
    @patch('apps.orders.views._get_store_for_user', return_value=_mock_store())
    def test_excecao_nao_exposta_no_body(self, _sf, _go, mock_task):
        mock_task.delay.side_effect = Exception(_SECRET)

        req = self.factory.post('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = CreateDeliveryRequestView.as_view()(
            req, store_slug='loja-test', order_id='order-uuid-222'
        )

        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(_SECRET, str(resp.data))
        self.assertNotIn('Uber internal', str(resp.data))
        self.assertNotIn('bearer-SUPERSECRET', str(resp.data))

    @patch('apps.orders.views.create_uber_delivery_request')
    @patch('apps.orders.views.get_object_or_404', return_value=_mock_order_create())
    @patch('apps.orders.views._get_store_for_user', return_value=_mock_store())
    def test_retorna_mensagem_generica(self, _sf, _go, mock_task):
        mock_task.delay.side_effect = Exception(_SECRET)

        req = self.factory.post('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = CreateDeliveryRequestView.as_view()(
            req, store_slug='loja-test', order_id='order-uuid-222'
        )

        self.assertIn('detail', resp.data)
        body = str(resp.data['detail'])
        self.assertGreater(len(body), 0)
        self.assertNotIn(_SECRET, body)


class DeliveryStatusStrELeakTest(SimpleTestCase):
    """delivery-request-status não expõe str(e) em HTTP 500."""

    def setUp(self):
        self.factory = APIRequestFactory()

    @patch('apps.orders.views.UberDeliveryClient')
    @patch('apps.orders.views.get_object_or_404', return_value=_mock_order_with_request())
    @patch('apps.orders.views._get_store_for_user', return_value=_mock_store())
    def test_excecao_nao_exposta_no_body(self, _sf, _go, mock_client_cls):
        mock_client_cls.return_value.poll_delivery_status.side_effect = Exception(_SECRET)

        req = self.factory.get('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = DeliveryRequestStatusView.as_view()(
            req, store_slug='loja-test', order_id='order-uuid-222'
        )

        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(_SECRET, str(resp.data))

    @patch('apps.orders.views.UberDeliveryClient')
    @patch('apps.orders.views.get_object_or_404', return_value=_mock_order_with_request())
    @patch('apps.orders.views._get_store_for_user', return_value=_mock_store())
    def test_retorna_mensagem_generica(self, _sf, _go, mock_client_cls):
        mock_client_cls.return_value.poll_delivery_status.side_effect = Exception(_SECRET)

        req = self.factory.get('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = DeliveryRequestStatusView.as_view()(
            req, store_slug='loja-test', order_id='order-uuid-222'
        )

        self.assertIn('detail', resp.data)
        self.assertNotIn(_SECRET, str(resp.data['detail']))


class CancelDeliveryStrELeakTest(SimpleTestCase):
    """cancel-delivery-request não expõe str(e) em HTTP 500."""

    def setUp(self):
        self.factory = APIRequestFactory()

    @patch('apps.orders.views.UberDeliveryClient')
    @patch('apps.orders.views.get_object_or_404', return_value=_mock_order_with_request())
    @patch('apps.orders.views._get_store_for_user', return_value=_mock_store())
    def test_excecao_nao_exposta_no_body(self, _sf, _go, mock_client_cls):
        mock_client_cls.return_value.cancel_delivery_request.side_effect = Exception(_SECRET)

        req = self.factory.delete('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = CancelDeliveryRequestView.as_view()(
            req, store_slug='loja-test', order_id='order-uuid-222'
        )

        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(_SECRET, str(resp.data))

    @patch('apps.orders.views.UberDeliveryClient')
    @patch('apps.orders.views.get_object_or_404', return_value=_mock_order_with_request())
    @patch('apps.orders.views._get_store_for_user', return_value=_mock_store())
    def test_retorna_mensagem_generica(self, _sf, _go, mock_client_cls):
        mock_client_cls.return_value.cancel_delivery_request.side_effect = Exception(_SECRET)

        req = self.factory.delete('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = CancelDeliveryRequestView.as_view()(
            req, store_slug='loja-test', order_id='order-uuid-222'
        )

        self.assertIn('detail', resp.data)
        self.assertNotIn(_SECRET, str(resp.data['detail']))
