"""
Token que EXISTE mas passou do TTL também não pode trancar o cliente fora.

Continuação de test_token_invalido_nao_tranca.py (27/ago). Aquele lote cobriu o
token que não existe no banco: o middleware deixa passar (`Token.DoesNotExist`)
e o DRF trata como visitante. Ficou de fora o caso do token REAL e velho — o
que todo cliente fiel tem, porque ele fez login há mais de 30 dias.

Nesse caso o `TokenExpirationMiddleware` devolve 401 direto, como middleware do
Django: antes da view, antes da permissão, antes de qualquer AllowAny. Ou seja,
derruba catálogo, carrinho, consulta de fidelidade — e o envio de OTP, que é
justamente o que tiraria o cliente da armadilha. Mesma porta trancada de
agosto, por outra fechadura.

Relato de produção (02/set): "OTP não tá funcionando, tá dando erro" e "coloquei
o número no cartão de fidelidade e nada mudou". Os dois eram esta linha:
    {"error": {"code": "token_expired", ...}}  → HTTP 401
numa rota `permission_classes = [AllowAny]`.

Crachá vencido não impede entrar numa porta aberta: o pedido segue como
visitante. Rota privada continua barrada — pela permissão, que é o lugar certo.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store


pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(
        username='dono-ttl', email='dono-ttl@example.com', password='x'
    )
    return Store.objects.create(name='TTL', slug='loja-ttl', owner=dono)


@pytest.fixture
def token_vencido(db):
    """Token real, do mesmo jeito que o do cliente: emitido e esquecido."""
    usuario = User.objects.create_user(
        username='cliente-antigo', email='cliente-antigo@example.com', password='x'
    )
    token = Token.objects.create(user=usuario)
    Token.objects.filter(pk=token.pk).update(
        created=timezone.now() - timedelta(days=400)
    )
    return token


@pytest.fixture
def cliente_com_token_vencido(token_vencido):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Token {token_vencido.key}')
    return c


class TestRotaPublicaComTokenVencido:
    def test_catalogo_abre(self, loja, cliente_com_token_vencido):
        r = cliente_com_token_vencido.get(f'/api/v1/stores/{loja.slug}/catalog/')
        assert r.status_code != 401, 'token vencido não pode fechar o cardápio'

    def test_envio_de_otp_nao_e_barrado(self, loja, cliente_com_token_vencido):
        # O pior caso: é o login que tira o cliente da armadilha.
        r = cliente_com_token_vencido.post(
            '/api/v1/auth/whatsapp/send/', {'phone': '63999999999'}, format='json'
        )
        assert r.status_code != 401

    def test_consulta_de_fidelidade_por_telefone_responde(self, loja, cliente_com_token_vencido):
        r = cliente_com_token_vencido.post(
            f'/api/v1/stores/{loja.slug}/loyalty/guest-status/',
            {'phone': '63999999999'},
            format='json',
        )
        assert r.status_code != 401

    def test_a_resposta_e_de_visitante_e_nao_de_porta_trancada(self, loja, cliente_com_token_vencido):
        r = cliente_com_token_vencido.get(f'/api/v1/stores/{loja.slug}/catalog/')
        assert r.status_code not in (401, 403)


class TestOQueEPrivadoContinuaPrivado:
    def test_token_vencido_nao_da_acesso_ao_que_exige_login(self, loja, cliente_com_token_vencido):
        # A correção não pode virar "token vencido continua valendo".
        r = cliente_com_token_vencido.get('/api/v1/auth/me/')
        assert r.status_code in (401, 403), 'privado tem de continuar privado'

    def test_token_dentro_do_prazo_continua_entrando(self, loja):
        usuario = User.objects.create_user(
            username='cliente-recente', email='cliente-recente@example.com', password='x'
        )
        token = Token.objects.create(user=usuario)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        r = c.get('/api/v1/auth/me/')
        assert r.status_code == 200, 'token novo não pode ser tratado como vencido'
