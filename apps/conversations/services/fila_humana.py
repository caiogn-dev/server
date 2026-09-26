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
    from apps.conversations.services.operacao_humana import esta_esperando

    return esta_esperando(conversa)


def _item(conversa, agora) -> dict:
    from apps.conversations.services import operacao_humana as op

    handover = getattr(conversa, 'handover', None)
    escreveu = conversa.last_customer_message_at
    motivo = op.motivo(conversa)
    desde = op.esperando_desde(conversa)
    return {
        'id': str(conversa.id),
        'telefone': conversa.phone_number,
        'nome': _nome(conversa),
        'motivo': motivo,
        'humano_desde': getattr(handover, 'last_transfer_at', None),
        'cliente_escreveu_em': escreveu,
        'esperando_desde': desde,
        'esperando_ha_segundos': op.segundos_desde(desde, agora),
        'minutos_esperando': op.segundos_desde(desde, agora) // 60,
        'ultima_mensagem': (getattr(conversa, 'anno_last_text', '') or '')[:160],
        'atendente': op.atendente(conversa),
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
    # Maior espera primeiro — é quem o atendente pega antes.
    esperando.sort(key=lambda i: -i['esperando_ha_segundos'])
    return {
        'esperando': esperando,
        'em_atendimento': em_atendimento,
        'total_esperando': len(esperando),
        'total_em_atendimento': len(em_atendimento),
        'resumo': {
            'esperando': len(esperando),
            'em_atendimento': len(em_atendimento),
            'mais_antiga_segundos': esperando[0]['esperando_ha_segundos'] if esperando else 0,
        },
    }
