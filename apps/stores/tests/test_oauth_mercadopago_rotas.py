"""
As duas pontas que faltavam no OAuth do Mercado Pago: autorizar e receber.

O `mercadopago_oauth.py` já sabia montar a URL, trocar o código e salvar o
gateway desde 10/ago — e nada disso era alcançável, porque NENHUMA rota
chamava o módulo (`grep oauth apps/stores/urls.py` voltava vazio). Ligar as
credenciais no ambiente não bastava: não havia por onde o lojista clicar nem
para onde o Mercado Pago devolver o código.

Duas assimetrias que os testes existem para travar:

1. `autorizar` é do DONO da loja (autenticada, escopada). `callback` é PÚBLICA
   — quem chega nela é o navegador do lojista vindo do Mercado Pago, sem
   sessão nossa. Exigir autenticação ali quebraria o fluxo inteiro em produção,
   e é o tipo de erro que só aparece no primeiro lojista real.

2. O `state` não pode ser só `loja:<slug>`. Slug é público e adivinhável: com
   ele, dá para induzir um lojista a autorizar a conta dele numa loja de
   terceiro (CSRF de conexão — a conta certa, plugada na loja errada). O state
   passa a carregar nonce de uso único com validade curta.
"""
import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.stores.models import StorePaymentGateway
from apps.stores.services import mercadopago_oauth
from apps.stores.tests.factories import make_store

AUTORIZAR = '/api/v1/stores/payments/gateways/oauth/autorizar/'
CALLBACK = '/api/v1/stores/payments/gateways/oauth/callback/'

LIGADO = dict(
    MP_OAUTH_CLIENT_ID='123456',
    MP_OAUTH_CLIENT_SECRET='segredo',
    MP_OAUTH_REDIRECT_URI='https://backend.pastita.com.br/api/v1/stores/payments/gateways/oauth/callback/',
)


@pytest.fixture(autouse=True)
def _limpa_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def loja(db):
    return make_store()


@pytest.fixture
def dono(loja):
    return loja.owner


@pytest.fixture
def cliente_logado(dono):
    c = APIClient()
    c.force_authenticate(user=dono)
    return c


# ── state com nonce ─────────────────────────────────────────────────────────

@override_settings(**LIGADO)
def test_state_nao_e_apenas_o_slug(loja):
    """Slug puro é adivinhável: permitiria plugar a conta na loja errada."""
    state = mercadopago_oauth.criar_state(loja)

    assert state != f'loja:{loja.slug}'
    assert len(state) >= 16


@override_settings(**LIGADO)
def test_state_valido_resolve_a_loja(loja):
    state = mercadopago_oauth.criar_state(loja)

    assert mercadopago_oauth.consumir_state(state) == loja.slug


@override_settings(**LIGADO)
def test_state_e_de_uso_unico(loja):
    """Replay do callback não pode reconectar a loja uma segunda vez."""
    state = mercadopago_oauth.criar_state(loja)
    mercadopago_oauth.consumir_state(state)

    assert mercadopago_oauth.consumir_state(state) == ''


@override_settings(**LIGADO)
def test_state_forjado_nao_resolve_loja(loja):
    assert mercadopago_oauth.consumir_state(f'loja:{loja.slug}') == ''
    assert mercadopago_oauth.consumir_state('qualquer-coisa') == ''
    assert mercadopago_oauth.consumir_state('') == ''


# ── autorizar ───────────────────────────────────────────────────────────────

def test_autorizar_exige_autenticacao(loja):
    resposta = APIClient().get(AUTORIZAR, {'store': str(loja.id)})

    assert resposta.status_code in (401, 403)


@override_settings(MP_OAUTH_CLIENT_ID='', MP_OAUTH_CLIENT_SECRET='')
def test_autorizar_avisa_quando_o_app_nao_esta_registrado(cliente_logado, loja):
    """Sem credencial, a tela precisa dizer o porquê — não estourar 500."""
    resposta = cliente_logado.get(AUTORIZAR, {'store': str(loja.id)})

    assert resposta.status_code == 503
    assert 'detail' in resposta.data


@override_settings(**LIGADO)
def test_autorizar_devolve_url_do_mercadopago(cliente_logado, loja):
    resposta = cliente_logado.get(AUTORIZAR, {'store': str(loja.id)})

    assert resposta.status_code == 200
    url = resposta.data['authorization_url']
    assert url.startswith('https://auth.mercadopago.com')
    assert 'client_id=123456' in url
    assert 'response_type=code' in url


@override_settings(**LIGADO)
def test_autorizar_recusa_loja_de_outro_dono(cliente_logado, db):
    """Escopo de loja não pode vazar: seria a conta de A ligada na loja de B."""
    alheia = make_store(slug='loja-de-outro')

    resposta = cliente_logado.get(AUTORIZAR, {'store': str(alheia.id)})

    assert resposta.status_code in (403, 404)


@override_settings(**LIGADO)
def test_autorizar_sem_store_recusa(cliente_logado):
    resposta = cliente_logado.get(AUTORIZAR)

    assert resposta.status_code == 400


# ── callback ────────────────────────────────────────────────────────────────

@override_settings(**LIGADO)
def test_callback_nao_exige_autenticacao(db):
    """Quem chega aqui é o navegador do lojista vindo do MP, sem sessão nossa."""
    resposta = APIClient().get(CALLBACK, {'code': 'x', 'state': 'invalido'})

    assert resposta.status_code not in (401, 403)


@override_settings(**LIGADO)
def test_callback_com_state_invalido_nao_cria_gateway(db):
    APIClient().get(CALLBACK, {'code': 'abc', 'state': 'forjado'})

    assert StorePaymentGateway.objects.count() == 0


@override_settings(**LIGADO)
def test_callback_feliz_salva_o_gateway_da_loja(loja, monkeypatch):
    state = mercadopago_oauth.criar_state(loja)
    monkeypatch.setattr(
        mercadopago_oauth, 'trocar_codigo_por_token',
        lambda codigo: {
            'access_token': 'APP_USR-da-agriao',
            'refresh_token': 'TG-refresh',
            'public_key': 'APP_USR-pk-da-agriao',
            'expires_in': 15552000,
            'user_id': 987654,
        },
    )

    resposta = APIClient().get(CALLBACK, {'code': 'codigo-do-mp', 'state': state})

    assert resposta.status_code in (302, 200)
    g = StorePaymentGateway.objects.get(store=loja)
    assert g.connection_type == StorePaymentGateway.ConnectionType.OAUTH
    assert g.access_token == 'APP_USR-da-agriao'
    assert g.refresh_token == 'TG-refresh'
    assert g.external_account_id == '987654'


@override_settings(**LIGADO)
def test_callback_guarda_a_public_key(loja, monkeypatch):
    """Sem a public key da MESMA conta, o cartão quebra: o token do cartão sai
    com a chave da plataforma e é cobrado com o token da loja — o MP recusa."""
    state = mercadopago_oauth.criar_state(loja)
    monkeypatch.setattr(
        mercadopago_oauth, 'trocar_codigo_por_token',
        lambda codigo: {
            'access_token': 'APP_USR-x', 'refresh_token': 'r',
            'public_key': 'APP_USR-pk-da-agriao', 'expires_in': 100, 'user_id': 1,
        },
    )

    APIClient().get(CALLBACK, {'code': 'c', 'state': state})

    assert StorePaymentGateway.objects.get(store=loja).public_key == 'APP_USR-pk-da-agriao'


@override_settings(**LIGADO)
def test_callback_sem_code_nao_cria_gateway(loja):
    state = mercadopago_oauth.criar_state(loja)

    APIClient().get(CALLBACK, {'state': state})

    assert StorePaymentGateway.objects.count() == 0


@override_settings(**LIGADO)
def test_callback_redireciona_para_o_painel(loja, monkeypatch):
    """O lojista precisa voltar para uma tela, não ver JSON cru."""
    state = mercadopago_oauth.criar_state(loja)
    monkeypatch.setattr(
        mercadopago_oauth, 'trocar_codigo_por_token',
        lambda codigo: {'access_token': 'a', 'refresh_token': 'r',
                        'expires_in': 100, 'user_id': 1},
    )

    resposta = APIClient().get(CALLBACK, {'code': 'c', 'state': state})

    assert resposta.status_code == 302
    assert 'cardapidex.com.br' in resposta['Location']


@override_settings(**LIGADO)
def test_falha_na_troca_do_codigo_nao_deixa_gateway_pela_metade(loja, monkeypatch):
    import requests

    state = mercadopago_oauth.criar_state(loja)

    def explode(codigo):
        raise requests.HTTPError('invalid_grant')

    monkeypatch.setattr(mercadopago_oauth, 'trocar_codigo_por_token', explode)

    resposta = APIClient().get(CALLBACK, {'code': 'c', 'state': state})

    assert resposta.status_code == 302
    assert StorePaymentGateway.objects.count() == 0
