"""O que a loja mandou sozinha — para o painel mostrar ao dono.

Fonte: `whatsapp_messages`. A partir de 19/09 toda mensagem automática sai
pelo canal com `metadata.automatico`/`evento`. Antes disso, só aviso de status
e convite de avaliação eram gravados, reconhecíveis pela `source`.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

ROTULOS = {
    'status': 'Status do pedido',
    'feedback_request': 'Pedido de avaliação',
    'pix_reminder': 'Lembrete de PIX',
    'cart_reminder': 'Carrinho do site',
    'session_cart_reminder': 'Carrinho no WhatsApp',
    'reengagement': 'Faz tempo que não pede',
}

_FONTES_DE_STATUS = ('order_status_notification', 'store_order_notification')

#: O que a Meta responde, dito para o dono. Os quatro cobrem 236 das 254
#: falhas de 30 dias medidas em 19/09.
ERROS_DA_META = {
    '131047': 'Não chegou: o cliente não fala com a loja há mais de 24 h, e fora '
              'dessa janela o WhatsApp só aceita modelo aprovado.',
    '130472': 'O WhatsApp segurou a mensagem: o número está num teste da Meta.',
    '131049': 'O WhatsApp barrou para não cansar o cliente com mensagem de empresa.',
    '131026': 'Não chegou: o número não tem WhatsApp ou não consegue receber.',
}

DIAS_PADRAO = 7
DIAS_MAXIMO = 90
LIMITE_DE_ITENS = 200


def _filtro_do_tipo(tipo: str) -> Q:
    if tipo == 'status':
        return Q(metadata__evento__startswith='order_') | Q(metadata__source__in=_FONTES_DE_STATUS)
    if tipo == 'feedback_request':
        return Q(metadata__evento=tipo) | Q(metadata__source='feedback_request')
    return Q(metadata__evento=tipo)


def _eh_automatica() -> Q:
    return (
        Q(metadata__automatico=True)
        | Q(metadata__source__in=_FONTES_DE_STATUS)
        | Q(metadata__source='feedback_request')
    )


def tipo_da_mensagem(metadata: dict) -> str:
    evento = (metadata or {}).get('evento') or ''
    fonte = (metadata or {}).get('source') or ''
    if evento.startswith('order_') or fonte in _FONTES_DE_STATUS:
        return 'status'
    if fonte == 'feedback_request':
        return 'feedback_request'
    return evento or 'outra'


def _erro(msg) -> tuple[str, str]:
    codigo = (msg.error_code or '').strip()
    tecnico = ' · '.join(p for p in (codigo, msg.error_message or '') if p)
    return ERROS_DA_META.get(codigo, msg.error_message or ''), tecnico


def _dias(valor) -> int:
    try:
        dias = int(valor)
    except (TypeError, ValueError):
        return DIAS_PADRAO
    return min(max(dias, 1), DIAS_MAXIMO)


def listar_enviadas(conversas, dias=None, tipo=None, agora=None) -> dict:
    """`conversas`: queryset já restrito ao que o usuário pode ver."""
    from apps.whatsapp.models import Message

    agora = agora or timezone.now()
    dias = _dias(dias)
    base = Message.objects.filter(
        conversation_id__in=conversas.order_by().values('pk'),
        direction='outbound',
        created_at__gte=agora - timedelta(days=dias),
    ).filter(_eh_automatica())

    resumo = {}
    for metadata, status in base.values_list('metadata', 'status'):
        chave = tipo_da_mensagem(metadata)
        linha = resumo.setdefault(chave, {
            'tipo': chave, 'rotulo': ROTULOS.get(chave, chave), 'total': 0, 'falharam': 0,
        })
        linha['total'] += 1
        if status == 'failed':
            linha['falharam'] += 1

    lista = base.select_related('conversation')
    if tipo:
        lista = lista.filter(_filtro_do_tipo(tipo))

    itens = []
    for msg in lista.order_by('-created_at')[:LIMITE_DE_ITENS]:
        chave = tipo_da_mensagem(msg.metadata)
        conversa = msg.conversation
        erro, erro_tecnico = _erro(msg)
        itens.append({
            'id': str(msg.id),
            'quando': msg.created_at,
            'tipo': chave,
            'rotulo': ROTULOS.get(chave, chave),
            'cliente': ((conversa.contact_name if conversa else '') or '').strip() or msg.to_number,
            'telefone': msg.to_number,
            'texto': (msg.text_body or '')[:300],
            'status': msg.status,
            'erro': erro,
            'erro_tecnico': erro_tecnico,
            'conversa_id': str(msg.conversation_id) if msg.conversation_id else None,
        })

    return {
        'dias': dias,
        'resumo': sorted(resumo.values(), key=lambda r: -r['total']),
        'itens': itens,
    }
