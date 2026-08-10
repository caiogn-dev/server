"""Quais cliques são continuação de um fluxo que o próprio bot começou.

Existe para ser a ÚNICA resposta a essa pergunta. Antes a decisão vivia
duplicada em `webhook_service._should_suppress_for_human_mode` e em
`unified_service._is_human_mode_transactional_step`, e as duas divergiram: o
webhook liberava `rating_` e o orquestrador não. O clique da cliente passava
pela primeira porta e morria na segunda, e ela recebia a mensagem de último
recurso no lugar do link de avaliação.

Regra: quando um atendente humano assume a conversa, a automação cala — mas um
botão que o bot mandou não é "falar por cima" do atendente, é o bot terminando
o que ele mesmo começou. Botão desconhecido continua suprimido: no modo humano
o padrão é o silêncio.
"""

#: Ids fixos do checkout determinístico (escrevem StoreOrder).
IDS_TRANSACIONAIS = frozenset({
    'order_delivery',
    'order_pickup',
    'pay_pix',
    'pay_card',
    'pay_pickup',
})

#: Prefixos de botão seguidos do id do objeto (`rating_5_<order_id>`).
PREFIXOS_DE_FLUXO_DO_BOT = (
    'add_',
    'product_',
    'rating_',
    'review_done_',
    'refer_friend_',
    'track_',
)


def eh_fluxo_do_bot(reply_id) -> bool:
    """True quando o clique é a continuação de um fluxo do próprio bot."""
    reply_id = str(reply_id or '')
    if not reply_id:
        return False
    return (
        reply_id in IDS_TRANSACIONAIS
        or reply_id.startswith(PREFIXOS_DE_FLUXO_DO_BOT)
    )
