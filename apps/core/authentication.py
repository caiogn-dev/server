"""
Autenticação por token que não tranca o visitante do lado de fora.
"""
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class TokenOuVisitante(TokenAuthentication):
    """
    Igual ao `TokenAuthentication` do DRF, com uma diferença: token inválido
    faz o pedido seguir como VISITANTE em vez de virar 401 na hora.

    ── POR QUE ────────────────────────────────────────────────────────────────
    Relato de produção em 27/ago/2026: cliente sem conseguir entrar na loja.
    Com um token velho no navegador, o DRF respondia 401 no CATÁLOGO, no
    CARRINHO e no envio do código de login — todos endpoints públicos.

    O motivo é a ordem: `TokenAuthentication` levanta `AuthenticationFailed`
    assim que a chave não bate, ANTES de a rota dizer que aceita anônimo. Um
    crachá vencido não deveria impedir alguém de entrar numa porta aberta.

    Para o cliente virava armadilha sem saída: a loja não abria, e a única
    porta para escapar era limpar os dados do site na mão — o que ninguém faz.
    Ele desiste e some, e a loja nunca fica sabendo.

    ── O QUE NÃO MUDA ─────────────────────────────────────────────────────────
    Rota que exige login continua barrando: sem usuário, `IsAuthenticated`
    recusa. Só muda QUEM recusa — a permissão, que sabe o que a rota precisa,
    em vez da autenticação, que não sabe.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            # Chave desconhecida, usuário desativado, header malformado: nada
            # disso é motivo para fechar uma porta que está aberta.
            return None
