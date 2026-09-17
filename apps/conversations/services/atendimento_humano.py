"""Responder é assumir o atendimento — não importa por onde.

Desde 06/ago responder pelo PAINEL já passava a conversa para humano
(`MessageViewSet._assumir_atendimento`). Responder pelo APP do WhatsApp
Business, não — e em coexistência (COEX) o app é justamente onde o dono
atende.

11/ago, conversa do Diogo: o dono respondeu pelo celular ("Oiii", "O pedido foi
feito pelo site?") e o bot continuou solto, respondendo por cima dele com
botões de cardápio duas vezes. O modo da conversa nunca saiu de 'auto' porque
nada olhava o eco do app.

Esta função existe para que o gesto valha o mesmo dos dois lados. Painel e eco
chamam daqui — se um dia a regra mudar (janela de volta ao bot, permissão por
loja), muda em um lugar só.
"""
import logging

logger = logging.getLogger(__name__)


def assumir_atendimento(conversa, origem: str) -> bool:
    """Passa a conversa para modo humano. True quando mudou algo.

    Nunca levanta: o atendimento (envio da mensagem, gravação do eco) já
    aconteceu — falhar aqui só esconderia isso de quem está atendendo.
    """
    from apps.conversations.models import Conversation

    if conversa is None:
        return False
    if conversa.mode == Conversation.ConversationMode.HUMAN:
        return False

    try:
        from apps.conversations.services import ConversationService

        ConversationService().switch_to_human(str(conversa.id))
        logger.info(
            '[handover] Atendente assumiu a conversa (%s)', origem,
            extra={'conversation_id': str(conversa.id), 'handover.origem': origem},
        )
        return True
    except Exception as exc:
        logger.error(
            '[handover] Falha ao assumir a conversa (%s): %s', origem, exc,
            exc_info=True, extra={'conversation_id': str(conversa.id)},
        )
        return False


def marcar_conversa_como_pendente(conversa) -> bool:
    """Sobe a conversa para o atendente pelo contador de não lidas.

    Direct (Instagram) e Messenger não têm modo humano nem HandoverRequest —
    esses vivem aqui, em cima de `Conversation`, que hoje é só WhatsApp. O que
    esses canais têm é o contador de não lidas do inbox. Quando a IA falha,
    é ele que faz a conversa aparecer para alguém responder à mão, em vez de
    mandar "Desculpe, tive um problema" para o cliente (17/set).

    Best-effort: a falha da IA já aconteceu; estourar aqui só a esconderia.
    """
    if conversa is None:
        return False
    try:
        from django.db.models import F

        type(conversa).objects.filter(pk=conversa.pk).update(
            unread_count=F('unread_count') + 1,
        )
        return True
    except Exception as exc:
        logger.warning('[handover] Falha ao marcar conversa como pendente: %s', exc, exc_info=True)
        return False
