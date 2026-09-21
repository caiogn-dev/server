"""Peças de serializer compartilhadas.

`validate_store` estava copiado 11 vezes em 4 apps — e as cópias já tinham
divergido: stores e automation deixavam o usuário anônimo passar reto,
marketing checava sempre, nutrition tinha texto próprio. Trava de segurança
copiada não envelhece junto: uma afrouxa e ninguém percebe até vazar loja de
cliente.
"""
from rest_framework import serializers

NAO_ENCONTRADA = 'Loja não encontrada'


def checar_loja_do_usuario(request, loja, mensagem: str = NAO_ENCONTRADA):
    """Devolve a loja se o usuário do pedido pode usá-la; senão, recusa.

    Sem `request` no contexto (shell, tarefa, teste) não há usuário para
    checar e não há IDOR: passa. Com pedido, exige usuário autenticado com
    vínculo — anônimo não passa.

    A recusa fala "não encontrada", e não "sem permissão": confirmar que a
    loja existe já é informação sobre o vizinho.
    """
    if request is None:
        return loja

    from apps.core.permissions import user_can_access_store

    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        raise serializers.ValidationError(mensagem)
    if not user_can_access_store(user, loja):
        raise serializers.ValidationError(mensagem)
    return loja


class LojaDoUsuarioMixin:
    """Dá `validate_store` ao serializer. Sobrescreva `mensagem_de_loja` se o
    campo apontar para outra coisa ("Categoria não encontrada")."""

    mensagem_de_loja = NAO_ENCONTRADA

    def validate_store(self, value):
        return checar_loja_do_usuario(
            self.context.get('request'), value, self.mensagem_de_loja,
        )
