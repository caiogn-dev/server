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

#: O que o dono lê na fila ao lado de cada conversa. Antes todas diziam
#: "Synced from conversation mode switch".
MOTIVOS = {
    'eco_do_app_business': 'Respondido pelo WhatsApp do celular',
    'painel': 'Respondido pelo painel',
    'falha_da_ia': 'A IA não conseguiu responder',
}


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

        ConversationService().switch_to_human(
            str(conversa.id), motivo=MOTIVOS.get(origem, origem),
        )
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


def devolver_ao_bot(conversa, motivo: str) -> bool:
    """Tira a conversa do modo humano. True quando mudou algo. Nunca levanta."""
    from apps.conversations.models import Conversation

    if conversa is None or conversa.mode != Conversation.ConversationMode.HUMAN:
        return False
    try:
        from apps.conversations.services import ConversationService

        ConversationService().switch_to_auto(str(conversa.id), motivo=motivo)
        conversa.refresh_from_db()
        logger.info(
            '[handover] Conversa devolvida ao bot (%s)', motivo,
            extra={'conversation_id': str(conversa.id)},
        )
        return True
    except Exception as exc:
        logger.error(
            '[handover] Falha ao devolver ao bot: %s', exc,
            exc_info=True, extra={'conversation_id': str(conversa.id)},
        )
        return False


def ultima_atividade_humana(conversa):
    """Quando alguém atendeu por último: a passagem para humano ou a última resposta."""
    handover = getattr(conversa, 'handover', None)
    marcos = [
        getattr(handover, 'last_transfer_at', None),
        conversa.last_agent_message_at,
    ]
    marcos = [m for m in marcos if m]
    return max(marcos) if marcos else None


def devolver_ao_bot_se_venceu(conversa, agora=None) -> bool:
    """Decisão do dono (19/09): o modo humano vale até o fim do dia.

    Antes não havia volta: uma resposta pelo celular emudecia o bot com aquele
    cliente para sempre (331 de 599 conversas presas em 19/09). A conta é
    feita na chegada da próxima mensagem do cliente — sem tarefa agendada:
    ninguém precisa do bot antes de o cliente voltar a falar.
    """
    from django.utils import timezone
    from apps.conversations.models import Conversation

    if conversa is None or conversa.mode != Conversation.ConversationMode.HUMAN:
        return False
    marco = ultima_atividade_humana(conversa)
    agora = agora or timezone.now()
    if marco is None:
        # Sem saber quando virou humana, não solta: soltar por engano é o bot
        # falando por cima de alguém. As presas antigas sem registro saem pelo
        # comando `soltar_modo_humano_parado`, com prévia.
        return False
    if timezone.localtime(marco).date() >= timezone.localtime(agora).date():
        return False
    return devolver_ao_bot(conversa, 'Modo humano venceu: novo dia, o bot voltou')
