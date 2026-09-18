"""
O corpo do webhook do Mercado Pago NÃO decide se o pedido foi pago.

A assinatura do MP cobre só `id;request-id;ts` — o corpo não é assinado — e o
`ts` não tem janela de validade na rota viva. Isso só é seguro porque a rota
relê o pagamento na API do MP e decide pela resposta: uma requisição assinada
repetida (replay) ou com o corpo adulterado provoca, no máximo, uma leitura extra.

Estes testes travam essa garantia. Se alguém "otimizar" pulando a consulta
quando o corpo já traz `status`, eles quebram.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.stores.models import Store

User = get_user_model()
PAYMENT_ID = '5550001112'


@pytest.fixture(autouse=True)
def limpa_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_corpo', password='x')
    return Store.objects.create(owner=dono, name='Loja Corpo', slug='loja-corpo-test')


def _sdk_que_diz(status_no_mp):
    sdk = MagicMock()
    sdk.payment.return_value.get.return_value = {
        'status': 200,
        'response': {'id': PAYMENT_ID, 'status': status_no_mp, 'external_reference': 'ORD-9'},
    }
    return sdk


@pytest.mark.django_db
class TestCorpoDoWebhookNaoMandaNoStatus:

    def _post_forjado(self, loja):
        # Corpo adulterado: diz 'approved' com o MP dizendo outra coisa.
        return APIClient().post(
            f'/webhooks/payments/mercadopago/{loja.slug}/?type=payment',
            {'type': 'payment', 'status': 'approved',
             'data': {'id': PAYMENT_ID, 'status': 'approved'}},
            format='json',
        )

    @patch('apps.stores.api.webhooks.checkout_service.process_payment_webhook')
    @patch('apps.stores.api.webhooks.checkout_service.get_payment_credentials')
    @patch('mercadopago.SDK')
    def test_status_vem_da_api_do_mp_e_nao_do_corpo(self, sdk_cls, creds, processa, loja):
        creds.return_value = {'access_token': 'tok'}
        sdk_cls.return_value = _sdk_que_diz('pending')
        processa.return_value = None

        resp = self._post_forjado(loja)

        assert resp.status_code == 200
        sdk_cls.return_value.payment.return_value.get.assert_called_once_with(PAYMENT_ID)
        status_aplicado = processa.call_args.args[1]
        assert status_aplicado == 'pending', (
            f"o corpo dizia 'approved' e o MP dizia 'pending'; aplicou {status_aplicado!r}"
        )

    @patch('apps.stores.api.webhooks.checkout_service.process_payment_webhook')
    @patch('apps.stores.api.webhooks.checkout_service.get_payment_credentials')
    @patch('mercadopago.SDK')
    def test_replay_da_mesma_notificacao_nao_processa_duas_vezes(
        self, sdk_cls, creds, processa, loja
    ):
        creds.return_value = {'access_token': 'tok'}
        sdk_cls.return_value = _sdk_que_diz('approved')
        processa.return_value = None

        self._post_forjado(loja)
        resp = self._post_forjado(loja)

        assert resp.json()['status'] == 'duplicate'
        assert processa.call_count == 1

    @patch('apps.stores.api.webhooks.checkout_service.get_payment_credentials')
    @patch('mercadopago.SDK')
    def test_mp_fora_do_ar_nao_vira_pagamento(self, sdk_cls, creds, loja):
        creds.return_value = {'access_token': 'tok'}
        sdk = MagicMock()
        sdk.payment.return_value.get.return_value = {'status': 500, 'response': {}}
        sdk_cls.return_value = sdk

        with patch('apps.stores.api.webhooks.checkout_service.process_payment_webhook') as processa:
            resp = self._post_forjado(loja)

        assert resp.json()['status'] == 'fetch_failed'
        processa.assert_not_called()


@pytest.mark.django_db
def test_rota_antiga_do_dispatcher_recusa_mp_sem_endpoint_cadastrado():
    """/webhooks/v1/mercadopago/ confia no status do corpo — por isso tem que
    ficar trancada. Em produção não há WebhookEndpoint de MP: 403 sempre."""
    resp = APIClient().post(
        '/webhooks/v1/mercadopago/',
        {'type': 'payment', 'status': 'approved', 'data': {'id': PAYMENT_ID}},
        format='json',
        HTTP_X_SIGNATURE='ts=1,v1=abc', HTTP_X_REQUEST_ID='r',
    )
    assert resp.status_code == 403
