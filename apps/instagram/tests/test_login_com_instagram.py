"""Login com Instagram: o lojista entra com a conta dele e a loja fica conectada.

Até 19/09 o Instagram nunca conectou ninguém (1 conta de teste, 0 mensagens):
- o painel abria o login do FACEBOOK, que exige Página e permissões de Página
  que a Meta recusou duas vezes — não serve para loja cliente;
- o retorno montava o endereço do painel com FRONTEND_URL, que é uma LISTA
  ("https://cardapidex.com.br,https://painel...") → janela caía em URL quebrada;
- o painel não tinha a rota /instagram/callback que avisa "terminou".

Fluxo novo (Business Login for Instagram): instagram.com/oauth/authorize →
/ig/callback troca o código em api.instagram.com, pega token de 60 dias,
lê a conta, assina os webhooks e volta para o painel.
"""
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.core.signing import TimestampSigner
from rest_framework.test import APIClient

from apps.instagram.models import InstagramAccount
from apps.instagram.services import login_instagram

CONFIG = dict(
    INSTAGRAM_LOGIN_APP_ID='ig-app-123',
    INSTAGRAM_LOGIN_APP_SECRET='ig-secret',
    INSTAGRAM_OAUTH_REDIRECT_URI='https://backend.exemplo/ig/callback',
    PAINEL_URL='https://painel.exemplo',
)


def _resposta(json_data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.raise_for_status.return_value = None
    return r


@pytest.fixture(autouse=True)
def _config(settings):
    for chave, valor in CONFIG.items():
        setattr(settings, chave, valor)


@pytest.fixture
def lojista(db):
    return get_user_model().objects.create_user(username='lojista-ig', password='x')


@pytest.fixture
def cliente(lojista):
    c = APIClient()
    c.force_authenticate(lojista)
    return c


@pytest.mark.django_db
class TestUrlDeConexao:

    def test_manda_para_o_login_do_instagram_com_as_permissoes_de_negocio(self, cliente):
        r = cliente.get('/api/v1/instagram/accounts/connect-url/')

        assert r.status_code == 200, r.content
        url = urlparse(r.json()['url'])
        assert url.netloc == 'www.instagram.com'
        q = parse_qs(url.query)
        assert q['client_id'] == ['ig-app-123']
        assert q['redirect_uri'] == ['https://backend.exemplo/ig/callback']
        assert set(q['scope'][0].split(',')) == {
            'instagram_business_basic',
            'instagram_business_manage_messages',
            'instagram_business_manage_comments',
        }
        assert q['state'][0].startswith(login_instagram.PREFIXO)

    def test_sem_app_do_instagram_configurado_diz_que_ainda_nao_esta_disponivel(self, cliente, settings):
        settings.INSTAGRAM_LOGIN_APP_ID = ''
        r = cliente.get('/api/v1/instagram/accounts/connect-url/')

        assert r.status_code == 503
        assert r.json()['codigo'] == 'instagram_indisponivel'


@pytest.mark.django_db
class TestRetornoDoLogin:

    def _state(self, user):
        return TimestampSigner().sign(f'{login_instagram.PREFIXO}{user.id}')

    def _rodar(self, state, code='codigo-ok'):
        post = MagicMock(side_effect=[
            _resposta({'access_token': 'curto', 'user_id': 17841400000000001}),  # troca do código
            _resposta({'success': True}),  # assinatura dos webhooks
        ])
        get = MagicMock(side_effect=[
            _resposta({'access_token': 'longo', 'expires_in': 5183944}),  # token de 60 dias
            _resposta({
                'user_id': '17841400000000001', 'username': 'cesaladas',
                'name': 'Cê Saladas', 'profile_picture_url': 'https://img/x.jpg',
                'followers_count': 1200, 'media_count': 80,
            }),
        ])
        with patch('apps.instagram.services.login_instagram.requests.post', post), \
                patch('apps.instagram.services.login_instagram.requests.get', get):
            r = APIClient().get('/ig/callback', {'code': code, 'state': state})
        return r, post, get

    def test_conecta_a_conta_e_volta_para_o_painel(self, lojista):
        r, post, _ = self._rodar(self._state(lojista))

        assert r.status_code == 302
        assert r['Location'] == 'https://painel.exemplo/instagram/callback?ig_connected=1'
        conta = InstagramAccount.objects.get(user=lojista)
        assert conta.instagram_business_id == '17841400000000001'
        assert conta.username == 'cesaladas'
        assert conta.access_token == 'longo'
        assert conta.is_active
        assert conta.token_expires_at is not None
        assert not conta.facebook_page_id

    def test_assina_comentarios_e_mensagens(self, lojista):
        _, post, _ = self._rodar(self._state(lojista))

        url, = post.call_args_list[1].args
        assert url.endswith('/me/subscribed_apps')
        campos = post.call_args_list[1].kwargs['params']['subscribed_fields'].split(',')
        # 'mentions' entrou em 21/set: é a marcação da loja em post/story, a
        # matéria-prima do sorteio "marque a gente para concorrer".
        assert {'messages', 'comments', 'mentions'} <= set(campos)

    def test_state_invalido_nao_conecta(self, lojista):
        r, post, _ = self._rodar('forjado')

        assert r['Location'].startswith('https://painel.exemplo/instagram/callback?ig_error=')
        post.assert_not_called()
        assert not InstagramAccount.objects.exists()

    def test_lojista_recusou_no_instagram(self, lojista):
        r = APIClient().get('/ig/callback', {'error': 'access_denied', 'state': self._state(lojista)})

        assert r['Location'].startswith('https://painel.exemplo/instagram/callback?ig_error=')

    def test_reconectar_atualiza_a_mesma_conta(self, lojista):
        self._rodar(self._state(lojista))
        self._rodar(self._state(lojista))

        assert InstagramAccount.objects.filter(user=lojista).count() == 1


@pytest.mark.django_db
class TestEnvioDaContaDoLogin:
    """Conta do Login com Instagram não tem Página: responde pelo graph.instagram.com."""

    def _conta(self, lojista, **extra):
        campos = dict(
            user=lojista, platform='instagram', instagram_business_id='17841400000000009',
            username='lojaig', access_token='token-ig', is_active=True,
        )
        campos.update(extra)
        return InstagramAccount.objects.create(**campos)

    def _enviar(self, conta):
        from apps.instagram.models import InstagramConversation
        from apps.instagram.services import InstagramAPI, InstagramDirectService

        conversa = InstagramConversation.objects.create(
            account=conta, participant_id='igsid-1', participant_username='cliente',
        )
        api = InstagramAPI(conta)
        resposta = _resposta({'message_id': 'mid.1', 'recipient_id': 'igsid-1'})
        with patch.object(api.session, 'request', return_value=resposta) as req:
            InstagramDirectService(api).send_text_message(str(conversa.id), 'Oi!')
        return req.call_args

    def test_responde_direct_sem_pagina_do_facebook(self, lojista, settings):
        chamada = self._enviar(self._conta(lojista))

        metodo, url = chamada.args
        assert metodo == 'POST'
        assert url == f'{settings.INSTAGRAM_GRAPH_URL}/17841400000000009/messages'
        assert chamada.kwargs['params']['access_token'] == 'token-ig'
        assert chamada.kwargs['json']['recipient'] == {'id': 'igsid-1'}

    def test_conta_antiga_com_pagina_segue_pelo_facebook(self, lojista, settings):
        conta = self._conta(lojista, facebook_page_id='pagina-1', page_access_token='token-pagina')

        metodo, url = self._enviar(conta).args
        assert url == f'{settings.META_GRAPH_URL}/pagina-1/messages'


@pytest.mark.django_db
def test_renova_o_token_da_conta_do_login_pelo_instagram(lojista):
    from apps.instagram.services import InstagramAPI

    conta = InstagramAccount.objects.create(
        user=lojista, platform='instagram', instagram_business_id='178414000000000077',
        username='renova', access_token='velho', is_active=True,
    )
    api = InstagramAPI(conta)
    with patch.object(api.session, 'get', return_value=_resposta({'access_token': 'novo', 'expires_in': 5184000})) as get:
        assert api.refresh_token() is True

    url = get.call_args.args[0]
    assert url == 'https://graph.instagram.com/refresh_access_token'
    assert get.call_args.kwargs['params'] == {'grant_type': 'ig_refresh_token', 'access_token': 'velho'}
    conta.refresh_from_db()
    assert conta.access_token == 'novo'
