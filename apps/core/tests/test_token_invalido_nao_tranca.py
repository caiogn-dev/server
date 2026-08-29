"""
Token velho no navegador não pode trancar o cliente FORA da loja.

Relato de produção (27/ago): o cliente não conseguia entrar. O console mostrava
401 no carrinho E no `auth/whatsapp/send/` — ou seja, falhava até o login que
consertaria a situação.

Reproduzido com um token lixo no header: **catálogo, carrinho e envio de OTP
respondiam 401**, todos endpoints públicos. É armadilha sem saída — a loja não
abre, e a única porta para sair é limpar os dados do site na mão, coisa que
nenhum cliente vai fazer: ele desiste e some.

A causa é do DRF: `TokenAuthentication` levanta `AuthenticationFailed` assim
que o token não bate, ANTES de a rota dizer que aceita anônimo. Um crachá
vencido não devia impedir alguém de entrar numa porta que está aberta.

A correção trata token inválido como VISITANTE. Rota que exige login continua
barrando — só que pelo caminho certo, a permissão.
"""
import pytest
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store


pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(
        username='dono-token', email='dono-token@example.com', password='x'
    )
    return Store.objects.create(name='Token', slug='loja-token', owner=dono)


LIXO = 'Token nao-existe-esse-token-123'


class TestRotaPublica:
    def test_catalogo_abre_com_token_vencido(self, loja):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=LIXO)
        r = c.get(f'/api/v1/stores/{loja.slug}/catalog/')
        assert r.status_code != 401, 'token velho não pode fechar o cardápio'

    def test_catalogo_abre_sem_token_nenhum(self, loja):
        r = APIClient().get(f'/api/v1/stores/{loja.slug}/catalog/')
        assert r.status_code != 401

    def test_envio_de_otp_nao_e_barrado_por_token_vencido(self, loja):
        # O pior caso: o login é justamente o que tira o cliente da armadilha.
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=LIXO)
        r = c.post('/api/v1/auth/whatsapp/send/', {'phone': '63999999999'}, format='json')
        assert r.status_code != 401

    def test_o_pedido_chega_como_visitante_e_nao_como_barrado(self, loja):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=LIXO)
        r = c.get(f'/api/v1/stores/{loja.slug}/catalog/')
        # O que importa é a NATUREZA da resposta: pode faltar a loja (404), não
        # pode ser porta trancada (401/403). Exigir 200 aqui amarraria o teste
        # ao que a rota de catálogo pede da loja, que é outro assunto.
        assert r.status_code not in (401, 403)


class TestRotaQueExigeLogin:
    def test_token_vencido_continua_sem_acesso_ao_que_e_privado(self, loja):
        # A correção NÃO pode abrir porta fechada: só muda por onde se barra.
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=LIXO)
        r = c.get('/api/v1/auth/me/')
        assert r.status_code in (401, 403), 'privado tem de continuar privado'

    def test_token_bom_continua_entrando(self, loja):
        from rest_framework.authtoken.models import Token
        usuario = User.objects.create_user(
            username='cliente-ok', email='cliente-ok@example.com', password='x'
        )
        token = Token.objects.create(user=usuario)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        r = c.get('/api/v1/auth/me/')
        assert r.status_code == 200


class TestFormatoEstranhoDoHeader:
    @pytest.mark.parametrize('header', [
        'Token',                    # sem a chave
        'Token a b c',              # partes demais
        'Bearer abc123',            # esquema de outro sistema
        'Token ',                   # chave vazia
    ])
    def test_header_malformado_tambem_vira_visitante(self, loja, header):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=header)
        r = c.get(f'/api/v1/stores/{loja.slug}/catalog/')
        assert r.status_code != 401
