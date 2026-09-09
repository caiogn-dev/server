"""A loja aceita este jeito de receber?

`delivery_enabled` / `pickup_enabled` existem no `Store` desde sempre, a API os
expõe e o cardápio já os respeita (`DeliveryBar.jsx`, com testes). Mas NADA
validava: esconder o botão no cardápio não fecha a porta. O bot do WhatsApp, o
PDV e qualquer POST direto continuavam criando pedido de entrega numa loja que
só faz retirada — e aí alguém precisa ligar para o cliente desmarcar.

Uma regra, um lugar: as duas portas de criação de pedido (o ViewSet
administrativo e o checkout do storefront) chamam daqui.
"""
from rest_framework import serializers

# `digital` é cobrança avulsa por link — não é entrega nem retirada, e barrá-la
# junto mataria a venda por link numa loja que só faz retirada.
_MODOS_CONTROLADOS = {
    'delivery': ('delivery_enabled', 'Esta loja não está fazendo entregas no momento.'),
    'pickup': ('pickup_enabled', 'Esta loja não está aceitando retirada no balcão.'),
}


def modo_permitido(store, delivery_method: str) -> bool:
    """`True` quando a loja aceita esse jeito de receber."""
    regra = _MODOS_CONTROLADOS.get((delivery_method or '').strip().lower())
    if not regra:
        return True
    campo, _ = regra
    return bool(getattr(store, campo, True))


def exigir_modo_permitido(store, delivery_method: str) -> None:
    """Levanta `ValidationError` quando a loja não aceita esse modo.

    A mensagem é para o CLIENTE ler: diz o que aconteceu sem expor
    configuração interna da loja.
    """
    if modo_permitido(store, delivery_method):
        return
    _, mensagem = _MODOS_CONTROLADOS[(delivery_method or '').strip().lower()]
    raise serializers.ValidationError({'delivery_method': mensagem})
