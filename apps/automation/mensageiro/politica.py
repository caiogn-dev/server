"""Quando a loja NÃO fala sozinha.

Regra do dono (21/09/2026): enquanto um atendente está na conversa — modo
humano —, nenhuma mensagem automática sai. Elas voltam quando a conversa volta
para o bot. Vale inclusive para aviso de status: o cliente que está conversando
com uma pessoa não recebe "saiu para entrega" por cima da conversa.

Fica no canal porque o canal é o único caminho de toda automática (fase 1) —
uma regra, um lugar.
"""
import logging

logger = logging.getLogger(__name__)


def silenciado(conta, telefone: str) -> bool:
    """Tem atendente humano nesta conversa agora?

    Falha na consulta devolve False de propósito: uma regra de silêncio que
    não conseguiu ser lida não pode engolir um aviso de pedido pago. Erra para
    o lado de falar.
    """
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.conversations.models import Conversation

    chave = chave_do_telefone(telefone)
    if not chave:
        return False

    try:
        conversas = list(
            Conversation.objects.filter(
                account_id=getattr(conta, 'id', None),
                mode=Conversation.ConversationMode.HUMAN,
            ).only('phone_number', 'mode')
        )
    except Exception as erro:  # noqa: BLE001 — conta inválida, banco fora
        logger.warning('Não deu para checar o modo humano: %s', erro)
        return False

    return any(chave_do_telefone(c.phone_number) == chave for c in conversas)
