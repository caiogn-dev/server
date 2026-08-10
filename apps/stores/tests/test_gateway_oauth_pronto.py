"""
Conexão do gateway da loja: token manual hoje, OAuth plugável depois.

Sem gateway próprio, o dinheiro do cliente final cai na conta da PLATAFORMA —
foi por isso que `PLATFORM_GATEWAY_STORE_SLUGS` virou allowlist. Só que não
existia como o lojista cadastrar o dele: o endpoint existe
(`/api/v1/stores/payments/gateways/`) e nunca teve tela.

O OAuth do Mercado Pago (modelo marketplace) exige app registrado, redirect URI
aprovada e refresh de token. Nada disso está feito, e não precisa estar para
vender: o token manual resolve hoje. O que estes testes garantem é que o OAuth
entra depois SEM migração nova e sem tocar no checkout — só ligando as
credenciais.
"""
import pytest
from django.test import override_settings

from apps.stores.models import StorePaymentGateway
from apps.stores.services import mercadopago_oauth
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store()


# ── O que funciona HOJE: token manual ────────────────────────────────────────

def test_token_manual_e_o_padrao(loja):
    g = StorePaymentGateway.objects.create(
        store=loja, name='MP da loja',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='APP_USR-123',
    )

    assert g.connection_type == StorePaymentGateway.ConnectionType.MANUAL


def test_gateway_manual_atende_o_checkout(loja):
    """O caminho do dinheiro tem que enxergar o gateway recém-cadastrado."""
    from apps.stores.services.checkout_service import CheckoutService

    StorePaymentGateway.objects.create(
        store=loja, name='MP da loja',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='APP_USR-DA-LOJA', is_enabled=True,
    )

    with override_settings(PLATFORM_GATEWAY_STORE_SLUGS=[]):
        creds = CheckoutService.get_payment_credentials(loja)

    assert creds['access_token'] == 'APP_USR-DA-LOJA'


# ── O que fica PRONTO: OAuth desligado por falta de credencial ───────────────

@override_settings(MP_OAUTH_CLIENT_ID='', MP_OAUTH_CLIENT_SECRET='')
def test_oauth_desligado_quando_nao_ha_app_registrado():
    assert mercadopago_oauth.esta_configurado() is False


@override_settings(MP_OAUTH_CLIENT_ID='', MP_OAUTH_CLIENT_SECRET='')
def test_url_de_autorizacao_recusa_quando_desligado(loja):
    with pytest.raises(mercadopago_oauth.OAuthNaoConfigurado):
        mercadopago_oauth.url_de_autorizacao(loja)


@override_settings(
    MP_OAUTH_CLIENT_ID='123456',
    MP_OAUTH_CLIENT_SECRET='segredo',
    MP_OAUTH_REDIRECT_URI='https://backend.pastita.com.br/api/v1/stores/payments/gateways/oauth/callback/',
)
def test_url_de_autorizacao_carrega_a_loja_no_state(loja):
    """Sem o slug no state, o callback não sabe de quem é o token."""
    url = mercadopago_oauth.url_de_autorizacao(loja)

    assert 'auth.mercadopago.com' in url
    assert 'client_id=123456' in url
    assert loja.slug in url
    assert 'response_type=code' in url


@override_settings(MP_OAUTH_CLIENT_ID='123456', MP_OAUTH_CLIENT_SECRET='segredo')
def test_salvar_conexao_oauth_marca_o_tipo_e_guarda_o_refresh(loja):
    g = mercadopago_oauth.salvar_conexao(
        loja,
        {'access_token': 'APP_USR-oauth', 'refresh_token': 'TG-refresh',
         'expires_in': 15552000, 'user_id': 987654},
    )

    assert g.connection_type == StorePaymentGateway.ConnectionType.OAUTH
    assert g.access_token == 'APP_USR-oauth'
    assert g.refresh_token == 'TG-refresh'
    assert g.external_account_id == '987654'
    assert g.token_expires_at is not None


@override_settings(MP_OAUTH_CLIENT_ID='123456', MP_OAUTH_CLIENT_SECRET='segredo')
def test_reconectar_atualiza_em_vez_de_duplicar(loja):
    """A constraint só permite um gateway MP habilitado por loja."""
    mercadopago_oauth.salvar_conexao(
        loja, {'access_token': 'primeiro', 'refresh_token': 'r1', 'expires_in': 100, 'user_id': 1},
    )
    mercadopago_oauth.salvar_conexao(
        loja, {'access_token': 'segundo', 'refresh_token': 'r2', 'expires_in': 100, 'user_id': 1},
    )

    gateways = StorePaymentGateway.objects.filter(
        store=loja, gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
    )
    assert gateways.count() == 1
    assert gateways.first().access_token == 'segundo'


def test_token_oauth_vencido_e_reconhecido(loja):
    """Token de OAuth expira; o manual não. Quem renova precisa saber disso."""
    from django.utils import timezone
    from datetime import timedelta

    g = StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='x', connection_type=StorePaymentGateway.ConnectionType.OAUTH,
        token_expires_at=timezone.now() - timedelta(days=1),
    )

    assert g.token_vencido is True


def test_token_manual_nunca_e_considerado_vencido(loja):
    g = StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='x',
    )

    assert g.token_vencido is False
