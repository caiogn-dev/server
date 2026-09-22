"""Quem está esperando uma pessoa responder — montado a partir da conversa.

A página "Fila humana" lia `HandoverRequest`, tabela que nada preenchia
(0 linhas em 19/09/2026). A verdade sempre esteve na conversa: modo humano +
o cliente escreveu depois da nossa última resposta = esperando.
"""
from django.utils import timezone

from apps.conversations.services.atendimento_humano import ultima_atividade_humana


def _nome(conversa) -> str:
    return (
        (conversa.contact_name or '').strip()
        or (getattr(conversa, 'anno_unified_name', '') or '').strip()
        or conversa.phone_number
    )


def _esta_esperando(conversa) -> bool:
    escreveu = conversa.last_customer_message_at
    if not escreveu:
        return False
    respondemos = conversa.last_agent_message_at
    return respondemos is None or escreveu > respondemos


def _item(conversa, agora) -> dict:
    handover = getattr(conversa, 'handover', None)
    escreveu = conversa.last_customer_message_at
    return {
        'id': str(conversa.id),
        'telefone': conversa.phone_number,
        'nome': _nome(conversa),
        'motivo': (getattr(handover, 'transfer_reason', '') or '').replace(
            'Synced from conversation mode switch', 'Passou para atendimento humano',
        ) or 'Passou para atendimento humano',
        'humano_desde': getattr(handover, 'last_transfer_at', None),
        'cliente_escreveu_em': escreveu,
        'minutos_esperando': (
            int((agora - escreveu).total_seconds() // 60)
            if escreveu and _esta_esperando(conversa) else 0
        ),
        'ultima_mensagem': (getattr(conversa, 'anno_last_text', '') or '')[:160],
    }


def montar_fila(conversas, agora=None) -> dict:
    """`conversas`: queryset já restrito ao que o usuário pode ver."""
    from apps.conversations.models import Conversation

    agora = agora or timezone.now()
    hoje = timezone.localtime(agora).date()
    esperando, em_atendimento = [], []
    for conversa in conversas.filter(mode=Conversation.ConversationMode.HUMAN):
        if _esta_esperando(conversa):
            esperando.append(_item(conversa, agora))
            continue
        marco = ultima_atividade_humana(conversa)
        # Humana parada de outro dia não é fila: volta ao bot na próxima
        # mensagem do cliente (decisão do dono, 19/09).
        if marco and timezone.localtime(marco).date() >= hoje:
            em_atendimento.append(_item(conversa, agora))
    esperando.sort(key=lambda i: i['cliente_escreveu_em'])
    return {
        'esperando': esperando,
        'em_atendimento': em_atendimento,
        'total_esperando': len(esperando),
        'total_em_atendimento': len(em_atendimento),
    }
