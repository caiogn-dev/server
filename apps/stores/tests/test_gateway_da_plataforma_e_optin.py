"""
Cair nas credenciais da plataforma tem que ser opt-in explícito.

`get_payment_credentials` terminava num fallback silencioso para
`settings.MERCADO_PAGO_ACCESS_TOKEN`. Consequência: toda loja sem gateway
próprio — hoje, 11 de 11 — recebe o dinheiro do cliente final na conta do dono
da plataforma. É intermediação de pagamento de terceiros sem contrato, e torna
falsa a frase "o PIX cai direto na sua conta" do material de venda.

O fallback continua existindo para as lojas do próprio dono (grandfather),
mas agora precisa estar declarado em PLATFORM_GATEWAY_STORE_SLUGS. Loja nova
que não configurou gateway falha alto, no cadastro, em vez de falhar baixo, no
extrato.
"""
import pytest
from django.test import override_settings

from apps.stores.models import StorePaymentGateway
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store()


@override_settings(
    MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA',
    PLATFORM_GATEWAY_STORE_SLUGS=[],
)
def test_loja_nova_sem_gateway_nao_usa_a_conta_da_plataforma(loja):
    creds = CheckoutService.get_payment_credentials(loja)

    assert creds is None, 'dinheiro de terceiro não pode cair na conta da plataforma em silêncio'


@override_settings(
    MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA',
    PLATFORM_GATEWAY_STORE_SLUGS=[],
)
def test_loja_com_gateway_proprio_recebe_no_proprio_token(loja):
    StorePaymentGateway.objects.create(
        store=loja,
        name='MP da loja',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='TOKEN-DA-LOJA',
        is_enabled=True,
    )

    creds = CheckoutService.get_payment_credentials(loja)

    assert creds['access_token'] == 'TOKEN-DA-LOJA'


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA')
def test_loja_do_proprio_dono_continua_funcionando(loja):
    """Grandfather: as lojas do dono usam a conta dele por definição."""
    with override_settings(PLATFORM_GATEWAY_STORE_SLUGS=[loja.slug]):
        creds = CheckoutService.get_payment_credentials(loja)

    assert creds['access_token'] == 'TOKEN-DA-PLATAFORMA'


@override_settings(
    MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA',
    PLATFORM_GATEWAY_STORE_SLUGS=[],
)
def test_gateway_desabilitado_nao_vaza_para_a_plataforma(loja):
    """Desligar o gateway não pode redirecionar a receita para o dono."""
    StorePaymentGateway.objects.create(
        store=loja,
        name='MP da loja',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='TOKEN-DA-LOJA',
        is_enabled=False,
    )

    assert CheckoutService.get_payment_credentials(loja) is None
