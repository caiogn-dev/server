"""
Testes de integração da assinatura SaaS MercadoPago — exercita os pontos de
entrada reais (HTTP + webhook), não só a camada de serviço:

 - POST /api/v1/stores/{slug}/subscribe/ (StoreSubscribeView)
 - MercadoPagoHandler.handle() → roteamento de preapproval + apply_preapproval_event
 - _verify_mercadopago_signature (HMAC fail-closed)

O SDK do MercadoPago é mockado no boundary externo; nada sai pra rede.
"""
import hashlib
import hmac
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth.models import User

from rest_framework.test import APIClient

from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service
from apps.webhooks.handlers.mercadopago_handler import (
    MercadoPagoHandler,
    _verify_mercadopago_signature,
)


def _fake_create_sdk(init_point='https://mp/checkout/abc', pid='pre_123', status_code=201):
    """SDK fake para preapproval().create() (criação da assinatura)."""
    sdk = MagicMock()
    sdk.preapproval().create.return_value = {
        'status': status_code,
        'response': {'id': pid, 'init_point': init_point},
    }
    return sdk


def _fake_get_sdk(mp_status):
    """SDK fake para preapproval().get() (consulta de status no webhook)."""
    sdk = MagicMock()
    sdk.preapproval().get.return_value = {'response': {'status': mp_status}}
    return sdk


class SubscribeEndpointTestCase(TestCase):
    """POST /stores/{slug}/subscribe/ — permissão, validação e persistência."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner,
            status=Store.StoreStatus.ACTIVE,
        )
        self.url = f'/api/v1/stores/{self.store.slug}/subscribe/'
        self.client = APIClient()

    def test_owner_assina_retorna_201_e_persiste(self):
        self.client.force_authenticate(user=self.owner)
        with patch.object(subscription_service, '_sdk', return_value=_fake_create_sdk()):
            resp = self.client.post(self.url, {'plan': 'pro'}, format='json')
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['preapproval_id'], 'pre_123')
        self.assertEqual(body['init_point'], 'https://mp/checkout/abc')
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.plan, 'pro')
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)

    def test_nao_autenticado_negado(self):
        resp = self.client.post(self.url, {'plan': 'pro'}, format='json')
        self.assertIn(resp.status_code, (401, 403))
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())

    def test_nao_dono_403(self):
        other = User.objects.create_user('other', 'other@x.com', 'x')
        self.client.force_authenticate(user=other)
        resp = self.client.post(self.url, {'plan': 'pro'}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())

    def test_superuser_pode_assinar(self):
        su = User.objects.create_superuser('su', 'su@x.com', 'x')
        self.client.force_authenticate(user=su)
        with patch.object(subscription_service, '_sdk', return_value=_fake_create_sdk()):
            resp = self.client.post(self.url, {'plan': 'starter'}, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_plano_invalido_400(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'plan': 'ouro'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())

    def test_loja_exempt_400_sem_assinatura(self):
        self.store.billing_exempt = True
        self.store.save()
        self.client.force_authenticate(user=self.owner)
        with patch.object(subscription_service, '_sdk', return_value=_fake_create_sdk()):
            resp = self.client.post(self.url, {'plan': 'pro'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())


class PreapprovalWebhookTestCase(TestCase):
    """MercadoPagoHandler — roteamento e aplicação de eventos de preapproval."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner,
            status=Store.StoreStatus.ACTIVE,
        )
        with patch.object(subscription_service, '_sdk', return_value=_fake_create_sdk()):
            subscription_service.create_subscription(self.store, 'pro', 'd@x.com', 'http://x')
        self.handler = MercadoPagoHandler()

    def _handle(self, event_type, data_id, mp_status='authorized'):
        payload = {'type': event_type, 'data': {'id': data_id} if data_id else {}}
        # O handler busca o status via subscription_service._sdk() (mesma fonte
        # de token da criação) — mockamos esse boundary.
        with patch.object(subscription_service, '_sdk', return_value=_fake_get_sdk(mp_status)):
            return self.handler.handle(None, payload, {})

    def test_subscription_authorized_ativa(self):
        result = self._handle('subscription_preapproval', 'pre_123', 'authorized')
        self.assertTrue(result['processed'])
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertTrue(sub.setup_fee_paid)
        self.assertIsNotNone(sub.started_at)

    def test_preapproval_cancelled_cancela(self):
        result = self._handle('preapproval', 'pre_123', 'cancelled')
        self.assertTrue(result['processed'])
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.CANCELED)
        self.assertIsNotNone(sub.canceled_at)

    def test_preapproval_paused_past_due(self):
        result = self._handle('subscription_authorized_payment', 'pre_123', 'paused')
        self.assertTrue(result['processed'])
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.PAST_DUE)

    def test_sem_data_id_nao_processa(self):
        result = self._handle('preapproval', None)
        self.assertFalse(result['processed'])
        self.assertEqual(result['reason'], 'no_preapproval_id')

    def test_preapproval_desconhecido_subscription_not_found(self):
        result = self._handle('preapproval', 'pre_INEXISTENTE', 'authorized')
        self.assertFalse(result['processed'])
        self.assertEqual(result['reason'], 'subscription_not_found')

    def test_evento_desconhecido_ignorado(self):
        # Não é payment/merchant_order/subscription/preapproval → não processa.
        result = self.handler.handle(None, {'type': 'chargeback', 'data': {'id': 'x'}}, {})
        self.assertFalse(result['processed'])
        self.assertEqual(result['reason'], 'unknown_event_type')


class PreapprovalWebhookViewRoutingTestCase(TestCase):
    """Bug de produção: o notification_url do preapproval aponta para
    /webhooks/payments/mercadopago/ (MercadoPagoWebhookView). Essa view PRECISA
    rotear eventos de preapproval — antes só tratava payment/merchant_order e o
    preapproval caía em 'ignored', então a assinatura nunca ativava."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner,
            status=Store.StoreStatus.ACTIVE,
        )
        with patch.object(subscription_service, '_sdk', return_value=_fake_create_sdk()):
            subscription_service.create_subscription(self.store, 'pro', 'd@x.com', 'http://x')
        self.client = APIClient()
        self.url = '/webhooks/payments/mercadopago/'

    def test_preapproval_authorized_ativa_via_view(self):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'pre_123'}}
        with patch('apps.webhooks.handlers.mercadopago_handler._verify_mercadopago_signature',
                   return_value=True), \
             patch.object(subscription_service, '_sdk', return_value=_fake_get_sdk('authorized')):
            resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, 200)
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.store.refresh_from_db()
        self.assertEqual(self.store.plan, 'pro')

    def test_preapproval_assinatura_invalida_rejeita_via_view(self):
        payload = {'type': 'subscription_preapproval', 'data': {'id': 'pre_123'}}
        with patch('apps.webhooks.handlers.mercadopago_handler._verify_mercadopago_signature',
                   return_value=False):
            resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, 401)
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)


class WebhookSignatureTestCase(TestCase):
    """_verify_mercadopago_signature — comportamento fail-closed do HMAC."""

    def setUp(self):
        self.factory = RequestFactory()

    def _signed_request(self, secret, data_id='pre_123', ts='123', request_id='req-1', v1=None):
        template = f"id:{data_id};request-id:{request_id};ts:{ts}"
        if v1 is None:
            v1 = hmac.new(secret.encode(), template.encode(), hashlib.sha256).hexdigest()
        return self.factory.post(
            '/webhooks/payments/mercadopago/',
            HTTP_X_SIGNATURE=f"ts={ts},v1={v1}",
            HTTP_X_REQUEST_ID=request_id,
        )

    @override_settings(DEBUG=False)
    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': ''}, clear=False)
    def test_sem_secret_em_producao_rejeita(self):
        req = self.factory.post('/webhooks/payments/mercadopago/')
        self.assertFalse(_verify_mercadopago_signature(req, {'data': {'id': 'pre_123'}}))

    @override_settings(DEBUG=True)
    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': ''}, clear=False)
    def test_sem_secret_em_debug_libera(self):
        req = self.factory.post('/webhooks/payments/mercadopago/')
        self.assertTrue(_verify_mercadopago_signature(req, {'data': {'id': 'pre_123'}}))

    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': 'shh'}, clear=False)
    def test_hmac_valido_aceita(self):
        payload = {'data': {'id': 'pre_123'}}
        req = self._signed_request('shh', data_id='pre_123')
        self.assertTrue(_verify_mercadopago_signature(req, payload))

    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': 'shh'}, clear=False)
    def test_hmac_invalido_rejeita(self):
        payload = {'data': {'id': 'pre_123'}}
        req = self._signed_request('shh', data_id='pre_123', v1='deadbeef')
        self.assertFalse(_verify_mercadopago_signature(req, payload))

    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': 'shh'}, clear=False)
    def test_sem_x_signature_rejeita(self):
        payload = {'data': {'id': 'pre_123'}}
        req = self.factory.post('/webhooks/payments/mercadopago/')
        self.assertFalse(_verify_mercadopago_signature(req, payload))

    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': 'shh'}, clear=False)
    def test_preapproval_data_id_na_query_corpo_vazio(self):
        """Regressão do 401: no subscription_preapproval o MP manda data.id só na
        query (corpo vazio) e assina o manifesto no formato oficial com ';' final
        e id em minúsculas. O verificador antigo lia data.id do corpo → HMAC vazio
        → 401 → assinatura presa em trialing."""
        ts, rid = '1704908010', 'req-abc'
        real_id = 'AB12cd34'  # alfanumérico com maiúsculas → MP normaliza p/ lower
        manifest = f"id:{real_id.lower()};request-id:{rid};ts:{ts};"
        v1 = hmac.new(b'shh', manifest.encode(), hashlib.sha256).hexdigest()
        req = self.factory.post(
            f'/webhooks/payments/mercadopago/?data.id={real_id}&type=subscription_preapproval',
            HTTP_X_SIGNATURE=f"ts={ts},v1={v1}",
            HTTP_X_REQUEST_ID=rid,
        )
        # payload (corpo) vazio — como o MP realmente envia nesses eventos.
        self.assertTrue(_verify_mercadopago_signature(req, {}))

    @patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': 'shh'}, clear=False)
    def test_preapproval_query_id_errado_rejeita(self):
        """Segurança: com o secret certo mas data.id/assinatura forjados, rejeita."""
        req = self.factory.post(
            '/webhooks/payments/mercadopago/?data.id=forjado&type=subscription_preapproval',
            HTTP_X_SIGNATURE="ts=1,v1=deadbeef",
            HTTP_X_REQUEST_ID='req-x',
        )
        self.assertFalse(_verify_mercadopago_signature(req, {}))
