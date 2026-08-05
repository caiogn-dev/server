"""
Loja que configura webhook_secret não pode ter 100% dos webhooks rejeitados.

Regressão (S2-ARCH-002): `_validate_signature` calculava HMAC do CORPO CRU e
comparava com o header inteiro `x-signature: ts=...,v1=...`. O Mercado Pago
assina outra coisa — o manifesto `id:<data.id>;request-id:<x-request-id>;ts:<ts>`.
Comparar 'ts=...,v1=...' contra um hexdigest dá False sempre, então bastava a
loja preencher o secret (que é exatamente o que o comando oficial de onboarding
`setup_mercadopago_webhook` manda fazer) para todo pagamento dela parar de ser
baixado — sem fallback, porque o poller não reconcilia link de pagamento.

A implementação correta já existia em apps/webhooks/handlers/mercadopago_handler,
só que amarrada ao secret GLOBAL. Estes testes travam as duas pontas: assinatura
válida da loja passa, assinatura forjada não.
"""
import hashlib
import hmac

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StorePaymentGateway

User = get_user_model()

PAYMENT_ID = '9988776655'
REQUEST_ID = 'req-uuid-abc-123'
TS = '1785000000'
SECRET_LOJA = 'S3CR3T-DA-LOJA'


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_sig', password='x')
    return Store.objects.create(owner=dono, name='Loja Sig', slug='loja-sig-test')


@pytest.fixture
def loja_com_secret(loja):
    StorePaymentGateway.objects.create(
        store=loja,
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        is_enabled=True,
        webhook_secret=SECRET_LOJA,
    )
    return loja


def _assina(secret, data_id=PAYMENT_ID, request_id=REQUEST_ID, ts=TS):
    """Gera o x-signature exatamente como o Mercado Pago gera."""
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts}"
    v1 = hmac.new(secret.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def _post(loja, assinatura=None):
    headers = {'HTTP_X_REQUEST_ID': REQUEST_ID}
    if assinatura is not None:
        headers['HTTP_X_SIGNATURE'] = assinatura
    return APIClient().post(
        f'/webhooks/payments/mercadopago/{loja.slug}/?type=payment&data.id={PAYMENT_ID}',
        {'type': 'payment', 'data': {'id': PAYMENT_ID}},
        format='json',
        **headers,
    )


@pytest.mark.django_db
class TestAssinaturaPorLoja:

    def test_assinatura_valida_da_loja_nao_e_rejeitada(self, loja_com_secret):
        """O caso que quebrava: secret certo, assinatura certa, e vinha 401."""
        resp = _post(loja_com_secret, _assina(SECRET_LOJA))
        assert resp.status_code != 401, (
            'webhook legítimo da loja foi rejeitado — todo pagamento dela some'
        )

    def test_assinatura_forjada_e_rejeitada(self, loja_com_secret):
        resp = _post(loja_com_secret, _assina('secret-errado'))
        assert resp.status_code == 401

    def test_sem_header_de_assinatura_e_rejeitado(self, loja_com_secret):
        resp = _post(loja_com_secret, assinatura=None)
        assert resp.status_code == 401

    def test_header_malformado_e_rejeitado(self, loja_com_secret):
        resp = _post(loja_com_secret, 'nao-e-formato-ts-v1')
        assert resp.status_code == 401

    def test_loja_sem_secret_continua_passando(self, loja):
        """Nenhuma loja hoje tem secret; não podemos quebrar quem já funciona."""
        resp = _post(loja, _assina(SECRET_LOJA))
        assert resp.status_code != 401
