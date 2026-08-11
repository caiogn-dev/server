"""O que é continuação de um fluxo que o próprio bot começou.

Existe para ser a ÚNICA resposta a essa pergunta. Antes a decisão vivia
duplicada em `webhook_service._should_suppress_for_human_mode` e em
`unified_service._is_human_mode_transactional_step`, e as duas divergiram: o
webhook liberava `rating_` e o orquestrador não. O clique da cliente passava
pela primeira porta e morria na segunda, e ela recebia a mensagem de último
recurso no lugar do link de avaliação.

Em 11/ago a MESMA divergência apareceu pela porta da localização: o webhook
liberava qualquer localização em modo humano, o orquestrador só libera quando
existe checkout esperando endereço. A Damery mandou a localização enquanto o
dono resolvia o endereço na mão, o orquestrador calou, ninguém respondeu e o
último recurso entrou por cima do atendente. Por isso `espera_endereco` também
mora aqui: quem pergunta são as duas camadas.

Regra: quando um atendente humano assume a conversa, a automação cala — mas um
botão que o bot mandou não é "falar por cima" do atendente, é o bot terminando
o que ele mesmo começou. Botão desconhecido continua suprimido: no modo humano
o padrão é o silêncio.
"""
import re

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


#: Status de sessão em que um checkout ainda pode ser retomado.
STATUS_DE_CHECKOUT_VIVO = ('active', 'cart_created', 'checkout', 'payment_pending')


def eh_fluxo_do_bot(reply_id) -> bool:
    """True quando o clique é a continuação de um fluxo do próprio bot."""
    reply_id = str(reply_id or '')
    if not reply_id:
        return False
    return (
        reply_id in IDS_TRANSACIONAIS
        or reply_id.startswith(PREFIXOS_DE_FLUXO_DO_BOT)
    )


def espera_endereco(conversation, company=None, store=None) -> bool:
    """True quando existe checkout deste cliente parado esperando o endereço.

    É o que separa "o bot pediu o endereço e a localização é a resposta dele"
    de "o cliente mandou a localização para o atendente que está falando com
    ele". Só o primeiro caso autoriza o bot a responder em modo humano.
    """
    from apps.automation.models import CustomerSession

    if conversation is None:
        return False

    telefone = getattr(conversation, 'phone_number', '') or ''
    digitos = re.sub(r'\D', '', telefone)
    candidatos = [telefone]
    if digitos:
        candidatos.extend([digitos, f'+{digitos}'])
    candidatos = [valor for valor in dict.fromkeys(candidatos) if valor]

    sessoes = CustomerSession.objects.filter(
        phone_number__in=candidatos,
        status__in=STATUS_DE_CHECKOUT_VIVO,
        cart_data__waiting_for_address=True,
    )
    if company is not None:
        sessoes = sessoes.filter(company=company)
    elif store is not None:
        sessoes = sessoes.filter(company__store=store)

    return sessoes.exists()
