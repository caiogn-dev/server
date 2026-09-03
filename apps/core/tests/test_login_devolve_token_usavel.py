"""Login tem que devolver um token que FUNCIONA.

O BUG, visto em produção em 03/09: o dono confirmou o código do WhatsApp, o
backend respondeu `valid: true` com um token — e todas as páginas seguiram
tratando-o como visitante. Ele logou três vezes, em três telas diferentes, e
nada mudou. A carteira continuou travada, e o cardápio continuou oferecendo
"entrar para sincronizar" para alguém que acabara de entrar.

A CAUSA: `Token.objects.get_or_create(user=...)` devolve o token EXISTENTE. Se
esse token já passou de `AUTH_TOKEN_TTL_DAYS` (30 dias), o
`TokenExpirationMiddleware` trata a requisição como anônima — corretamente, é
o que ele existe para fazer. O resultado é um login que responde "sucesso",
entrega uma credencial morta e não autentica ninguém.

O token do dono tinha 36 dias. Isso atinge TODO cliente que logou há mais de
30 dias: para ele, o login simplesmente parou de funcionar, sem mensagem de
erro nenhuma — o pior tipo de falha, porque a interface parece certa.

A REGRA: autenticar com sucesso PRODUZ credencial usável. Token vencido é
substituído, nunca reaproveitado.
"""
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.core.auth.views import _token_utilizavel

User = get_user_model()
TTL = getattr(settings, 'AUTH_TOKEN_TTL_DAYS', 30)


def _envelhecer(token, dias):
    """`created` é auto_now_add: só dá para envelhecer por update direto."""
    Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=dias))
    token.refresh_from_db()
    return token


@pytest.mark.django_db
class TestTokenDeLogin:

    def test_token_vencido_e_substituido(self):
        """O caso do dono: token de 36 dias, TTL de 30."""
        user = User.objects.create_user(username='cliente_5563991386719', password='x')
        antigo = _envelhecer(Token.objects.create(user=user), TTL + 6)
        chave_antiga = antigo.key

        novo = _token_utilizavel(user)

        assert novo.key != chave_antiga, 'devolveu o mesmo token vencido'
        assert Token.objects.filter(user=user).count() == 1, 'sobrou token órfão'

    def test_o_token_devolvido_sobrevive_ao_middleware(self):
        """O que de fato importa: o token do login não pode ser barrado pelo
        próprio middleware de expiração meio segundo depois."""
        user = User.objects.create_user(username='cliente_5563991386714', password='x')
        _envelhecer(Token.objects.create(user=user), TTL + 6)

        idade = (timezone.now() - _token_utilizavel(user).created).days
        assert idade < TTL, f'login devolveu token com {idade} dias, TTL é {TTL}'

    def test_token_no_prazo_e_reaproveitado(self):
        """Não rotacionar à toa: trocar o token de quem está no prazo
        derrubaria a sessão do outro aparelho da pessoa sem motivo nenhum."""
        user = User.objects.create_user(username='cliente_5563991386712', password='x')
        atual = _envelhecer(Token.objects.create(user=user), 3)

        assert _token_utilizavel(user).key == atual.key

    def test_usuario_sem_token_ganha_um(self):
        user = User.objects.create_user(username='cliente_5563991386713', password='x')

        assert _token_utilizavel(user).key
        assert Token.objects.filter(user=user).count() == 1
