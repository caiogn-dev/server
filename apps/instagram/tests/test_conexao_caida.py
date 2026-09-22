"""Conta com token morto não pode aparecer como "Funcionando".

Em 21/09 a Conexões mostrava o Instagram @cesalada verde e funcionando; o
token era do caminho antigo (login do Facebook) e estava vencido — toda
chamada respondia "token inválido". O lojista não tinha como saber que o canal
estava mudo.
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.instagram.models import InstagramAccount
from apps.instagram.services.instagram_api import InstagramAPI, InstagramAPIException


@pytest.fixture
def conta(db):
    user = get_user_model().objects.create_user(username='dono-conexao', password='x')
    return InstagramAccount.objects.create(
        user=user, username='loja', instagram_business_id='ig-9', access_token='morto',
    )


class _Resposta:
    content = b'{}'
    status_code = 400

    def __init__(self, code):
        self._code = code

    def json(self):
        return {'error': {'code': self._code, 'message': 'token'}}

    def raise_for_status(self):
        import requests
        raise requests.exceptions.HTTPError('400')


def test_token_invalido_marca_a_conta(conta, monkeypatch):
    api = InstagramAPI(conta)
    monkeypatch.setattr(api.session, 'get', lambda *a, **k: _Resposta(190))

    with pytest.raises(InstagramAPIException):
        api.get('qualquer')

    conta.refresh_from_db()
    assert conta.token_invalido_em is not None


def test_chamada_boa_limpa_a_marca(conta, monkeypatch):
    conta.token_invalido_em = timezone.now()
    conta.save(update_fields=['token_invalido_em'])

    class Ok:
        content = b'{}'
        status_code = 200

        def json(self):
            return {'ok': True}

        def raise_for_status(self):
            return None

    api = InstagramAPI(conta)
    monkeypatch.setattr(api.session, 'get', lambda *a, **k: Ok())
    api.get('qualquer')

    conta.refresh_from_db()
    assert conta.token_invalido_em is None


def test_a_api_conta_pro_painel_que_a_conexao_caiu(conta, monkeypatch):
    from rest_framework.test import APIClient

    conta.token_invalido_em = timezone.now()
    conta.save(update_fields=['token_invalido_em'])
    cliente = APIClient()
    cliente.force_authenticate(user=conta.user)

    r = cliente.get('/api/v1/instagram/accounts/')

    dados = r.data['results'] if 'results' in r.data else r.data
    assert dados[0]['precisa_reconectar'] is True
