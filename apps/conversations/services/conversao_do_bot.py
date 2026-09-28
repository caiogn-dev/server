"""Conversão do bot — quantas conversas viram pedido, e onde a venda para.

A régua de qualquer agente novo. Medido em 28/09 (Cê Saladas, 30 dias):
186 conversas, 10 pedidos pelo WhatsApp, 144 transferências para atendente,
16 carrinhos parados — e nada disso era tela.

Definições:
- conversa: teve mensagem de cliente na janela (`last_customer_message_at`);
- pedido: `StoreOrder.source == 'whatsapp'` na janela (o site não conta);
- receita: só o que a régua de dinheiro considera receita (pago, não cancelado);
- perdida: conversa sem pedido do mesmo telefone na janela, classificada por
  prioridade — foi para atendente > deixou carrinho > o bot falhou > só perguntou.
"""
from collections import Counter
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .nao_entendi import falha_de_verdade
from .operacao_humana import normalizar

LIMITE_DE_PERDIDAS = 40


def _janela(dias):
    try:
        dias = max(1, min(int(dias or 30), 90))
    except (TypeError, ValueError):
        dias = 30
    return dias, timezone.now() - timedelta(days=dias)


def _telefone(valor) -> str:
    return ''.join(ch for ch in str(valor or '') if ch.isdigit())


def funil(lojas, dias=30) -> dict:
    from apps.automation.models import CustomerSession, IntentLog
    from apps.conversations.models import Conversation
    from apps.handover.models import ConversationHandover
    from apps.stores.metrics.definicoes import apenas_receita, soma_de_venda
    from apps.stores.models import StoreOrder
    from apps.whatsapp.models import Message

    dias, desde = _janela(dias)
    lojas = list(lojas)
    lojas_ids = [l.id for l in lojas]
    contas_ids = [l.whatsapp_account_id for l in lojas if l.whatsapp_account_id]

    conversas = (
        Conversation.objects
        .filter(account_id__in=contas_ids, last_customer_message_at__gte=desde)
        .order_by('-last_customer_message_at')
    )
    pedidos = StoreOrder.objects.filter(store_id__in=lojas_ids, created_at__gte=desde, source='whatsapp')
    telefones_com_pedido = {_telefone(t) for t in pedidos.values_list('customer_phone', flat=True)}
    receita = apenas_receita(pedidos).aggregate(v=soma_de_venda())['v']

    handovers = ConversationHandover.objects.filter(
        conversation__account_id__in=contas_ids, created_at__gte=desde,
    )
    motivos = Counter(handovers.values_list('transfer_reason', flat=True))
    conversas_com_atendente = set(handovers.values_list('conversation_id', flat=True))

    sessoes_paradas = CustomerSession.objects.filter(
        company__store_id__in=lojas_ids, updated_at__gte=desde, cart_items_count__gt=0, order__isnull=True,
    )
    telefones_com_carrinho = {_telefone(t) for t in sessoes_paradas.values_list('phone_number', flat=True)}

    falhas = IntentLog.objects.filter(company__store_id__in=lojas_ids, created_at__gte=desde)
    telefones_com_falha = {
        _telefone(tel) for tel, msg, resp in falhas.values_list('phone_number', 'message_text', 'response_text')
        if falha_de_verdade(msg, resp)
    }

    # Série por dia (conversas e pedidos), do dia mais antigo ao de hoje.
    hoje = timezone.localdate()
    por_dia = {hoje - timedelta(days=i): {'conversas': 0, 'pedidos': 0} for i in range(dias)}
    for quando in conversas.values_list('last_customer_message_at', flat=True):
        d = timezone.localtime(quando).date()
        if d in por_dia:
            por_dia[d]['conversas'] += 1
    for quando in pedidos.values_list('created_at', flat=True):
        d = timezone.localtime(quando).date()
        if d in por_dia:
            por_dia[d]['pedidos'] += 1
    serie = [{'dia': d.isoformat(), **v} for d, v in sorted(por_dia.items())]

    perdidas = []
    for conv in conversas.only('id', 'phone_number', 'contact_name', 'last_customer_message_at'):
        tel = _telefone(conv.phone_number)
        if tel in telefones_com_pedido:
            continue
        if conv.id in conversas_com_atendente:
            motivo = 'atendente'
        elif tel in telefones_com_carrinho:
            motivo = 'carrinho'
        elif tel in telefones_com_falha:
            motivo = 'bot_falhou'
        else:
            motivo = 'so_perguntou'
        perdidas.append({
            'conversa_id': str(conv.id), 'telefone': conv.phone_number, 'nome': conv.contact_name or '',
            'quando': conv.last_customer_message_at.isoformat() if conv.last_customer_message_at else None,
            'motivo': motivo, 'ultima_mensagem': '',
        })
        if len(perdidas) >= LIMITE_DE_PERDIDAS:
            break
    if perdidas:
        ids = [p['conversa_id'] for p in perdidas]
        ultimas = {}
        for cid, texto in (
            Message.objects.filter(conversation_id__in=ids, direction='inbound')
            .order_by('conversation_id', '-created_at').values_list('conversation_id', 'text_body')
        ):
            ultimas.setdefault(str(cid), (texto or '').strip())
        for p in perdidas:
            p['ultima_mensagem'] = ultimas.get(p['conversa_id'], '')[:200]

    total_conversas = conversas.count()
    total_pedidos = pedidos.count()
    return {
        'dias': dias,
        'conversas': total_conversas,
        'pedidos': total_pedidos,
        'receita': str(receita),
        'taxa': round(100.0 * total_pedidos / total_conversas, 1) if total_conversas else 0,
        'para_atendente': handovers.count(),
        'carrinho_parado': sessoes_paradas.count(),
        'bot_falhou': len(telefones_com_falha),
        'motivos_de_atendente': [
            {'motivo': m or 'Sem motivo registrado', 'vezes': n} for m, n in motivos.most_common(8)
        ],
        'serie': serie,
        'perdidas': perdidas,
    }
