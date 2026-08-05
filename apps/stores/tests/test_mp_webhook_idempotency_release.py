"""
Um pagamento aprovado não pode sumir por causa de um erro transitório.

Regressão: a chave de idempotência era reivindicada ANTES de processar e o
`except` do post() devolvia 200. Se o processamento estourasse (deadlock, conexão
do pgbouncer derrubada num deploy, timeout), o MP considerava entregue e nunca
reenviava; um reenvio manual caía no ramo 'duplicate'; e o poller de reconciliação
não alcançava, porque a janela era igual ao TTL da chave. Fim da linha:
`check_pending_payments` cancelava o pedido pago em 24h.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.stores.models import Store

User = get_user_model()
PAYMENT_ID = '1234567890'


@pytest.fixture(autouse=True)
def limpa_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_wh', password='x')
    return Store.objects.create(owner=dono, name='Loja WH', slug='loja-wh-test')


def _sdk_devolvendo(status_pagamento='approved'):
    """SDK falso que devolve um pagamento aprovado."""
    sdk = MagicMock()
    sdk.payment.return_value.get.return_value = {
        'status': 200,
        'response': {'id': PAYMENT_ID, 'status': status_pagamento, 'external_reference': 'ORD-1'},
    }
    return sdk


@pytest.mark.django_db
class TestLiberacaoDaChaveDeIdempotencia:

    def _post(self, loja):
        return APIClient().post(
            f'/webhooks/payments/mercadopago/{loja.slug}/?type=payment',
            {'type': 'payment', 'data': {'id': PAYMENT_ID}},
            format='json',
        )

    @patch('apps.stores.api.webhooks.checkout_service.process_payment_webhook')
    @patch('apps.stores.api.webhooks.checkout_service.get_payment_credentials')
    @patch('mercadopago.SDK')
    def test_erro_no_processamento_devolve_5xx_para_o_mp_reenviar(
        self, sdk_cls, creds, processa, loja
    ):
        creds.return_value = {'access_token': 'tok'}
        sdk_cls.return_value = _sdk_devolvendo()
        processa.side_effect = RuntimeError('conexão derrubada no meio da transação')

        resp = self._post(loja)

        # 200 aqui fazia o MP marcar como entregue e nunca mais tentar.
        assert resp.status_code >= 500, f'esperado 5xx, veio {resp.status_code}'

    @patch('apps.stores.api.webhooks.checkout_service.process_payment_webhook')
    @patch('apps.stores.api.webhooks.checkout_service.get_payment_credentials')
    @patch('mercadopago.SDK')
    def test_apos_falhar_o_reenvio_reprocessa_em_vez_de_cair_em_duplicate(
        self, sdk_cls, creds, processa, loja
    ):
        creds.return_value = {'access_token': 'tok'}
        sdk_cls.return_value = _sdk_devolvendo()

        processa.side_effect = RuntimeError('deadlock')
        self._post(loja)                      # 1ª entrega: estoura

        processa.side_effect = None
        processa.return_value = None
        self._post(loja)                      # reenvio do MP, banco saudável

        assert processa.call_count == 2, (
            'o reenvio não reprocessou — a chave de idempotência não foi liberada'
        )

    @patch('apps.stores.api.webhooks.checkout_service.process_payment_webhook')
    @patch('apps.stores.api.webhooks.checkout_service.get_payment_credentials')
    @patch('mercadopago.SDK')
    def test_sucesso_continua_bloqueando_reenvio_duplicado(
        self, sdk_cls, creds, processa, loja
    ):
        """A proteção contra processamento duplo tem que continuar valendo."""
        creds.return_value = {'access_token': 'tok'}
        sdk_cls.return_value = _sdk_devolvendo()
        processa.return_value = None

        self._post(loja)
        self._post(loja)

        assert processa.call_count == 1, 'webhook duplicado foi processado duas vezes'


@pytest.mark.django_db
class TestJanelaDoPoller:

    def test_janela_de_reconciliacao_e_maior_que_o_ttl_da_chave(self):
        """
        Se a janela for <= TTL (3600s), o poller nunca alcança um pagamento que o
        webhook perdeu: quando a chave expira, o StorePayment (criado ANTES do
        webhook) já saiu da janela.
        """
        import inspect
        from apps.stores import tasks

        fonte = inspect.getsource(tasks.reconcile_pending_pix_payments)
        assert 'timedelta(hours=24)' in fonte, (
            'a janela do poller precisa ser bem maior que o TTL de 3600s da chave'
        )
        assert 'hours=1)' not in fonte.replace('hours=24)', ''), 'janela de 1h ainda presente'
