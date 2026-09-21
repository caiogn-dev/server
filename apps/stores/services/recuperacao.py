"""O painel do recuperador de vendas: quanto ficou no carrinho e quanto voltou.

Os lembretes de carrinho rodam desde sempre e ninguém vê o resultado. Sem
estes números a loja não sabe se o recurso paga o incômodo — e "oportunidade
perdida em reais" é o número que faz o dono agir.

REGRA DE RECUPERAÇÃO

O carrinho conta como recuperado quando a MESMA pessoa faz um pedido DEPOIS do
abandono. Sem o "depois", qualquer pedido do dia contaria e o painel viraria
propaganda enganosa — o dono acharia que o lembrete trouxe gente que já tinha
comprado antes.

A identidade da pessoa é `chave_do_telefone`, a mesma da campanha e da
deduplicação de contatos: o cliente chega com e sem DDI, com e sem nono
dígito, e sem colapsar isso metade das recuperações some.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.db.models import Max
from django.utils import timezone

from apps.campaigns.services.contatos import chave_do_telefone

#: Os eventos que o mensageiro grava quando manda lembrete de carrinho.
#: Dois, porque há dois carrinhos: o do site (StoreCart) e o do bot
#: (CustomerSession).
EVENTOS_DE_LEMBRETE = ('cart_reminder', 'session_cart_reminder')


def _telefone_do_carrinho(carrinho) -> str:
    meta = carrinho.metadata or {}
    return (
        meta.get('customer_phone')
        or meta.get('phone_number')
        or getattr(carrinho.user, 'phone_number', '')
        or ''
    )


def painel_de_recuperacao(
    store_ids: Iterable,
    dias: int = 30,
    account_ids: Optional[Iterable] = None,
    agora=None,
) -> dict:
    """Os números do período, prontos para a tela."""
    from apps.stores.models.cart import StoreCart
    from apps.stores.models.order import StoreOrder

    agora = agora or timezone.now()
    desde = agora - timedelta(days=dias)
    lojas = list(store_ids)

    carrinhos = list(
        StoreCart.objects
        .filter(store_id__in=lojas, updated_at__gte=desde, updated_at__lte=agora)
        .prefetch_related('items__product', 'items__variant')
        .select_related('user')
    )

    # Carrinho SEM telefone não tem para onde mandar lembrete. Medido em
    # 21/09 na Cê Saladas: 404 carrinhos em 30 dias, 108 com itens, TRÊS com
    # telefone — a loja é guest-first e o telefone só aparece no checkout.
    # Sem este número, a taxa de recuperação baixa parece fracasso do texto do
    # lembrete, quando o lembrete nem chegou a existir.
    sem_telefone = sum(
        1 for c in carrinhos
        if c.items.exists() and not chave_do_telefone(_telefone_do_carrinho(c))
    )
    # Só o carrinho que virou lembrete: carrinho de 2 minutos atrás ainda está
    # sendo montado, não foi abandonado.
    abandonados = [
        c for c in carrinhos
        if (c.metadata or {}).get('reminder_30min_sent')
        or (c.metadata or {}).get('reminder_2h_sent')
        or (c.metadata or {}).get('reminder_24h_sent')
    ]

    # Último pedido de cada pessoa no período, por chave de telefone.
    ultimo_pedido: dict = {}
    pedidos = (
        StoreOrder.objects
        .filter(store_id__in=lojas, created_at__gte=desde)
        .exclude(customer_phone='')
        .values('customer_phone')
        .annotate(quando=Max('created_at'))
    )
    for linha in pedidos:
        chave = chave_do_telefone(linha['customer_phone'])
        if chave:
            atual = ultimo_pedido.get(chave)
            ultimo_pedido[chave] = max(atual, linha['quando']) if atual else linha['quando']

    valor_abandonado = Decimal('0')
    valor_recuperado = Decimal('0')
    recuperados = 0

    for carrinho in abandonados:
        valor = Decimal(str(carrinho.subtotal or 0))
        valor_abandonado += valor

        chave = chave_do_telefone(_telefone_do_carrinho(carrinho))
        quando = ultimo_pedido.get(chave) if chave else None
        if quando and quando > carrinho.updated_at:
            recuperados += 1
            # O que o cliente de fato gastou depois, não o que estava no
            # carrinho: o carrinho é intenção, o pedido é dinheiro.
            gasto = (
                StoreOrder.objects
                .filter(store_id__in=lojas, created_at=quando)
                .values_list('total', flat=True)
                .first()
            )
            valor_recuperado += Decimal(str(gasto or 0))

    mensagens = 0
    if account_ids:
        from apps.whatsapp.models import Message

        mensagens = (
            Message.objects
            .filter(
                account_id__in=list(account_ids),
                created_at__gte=desde,
                metadata__evento__in=list(EVENTOS_DE_LEMBRETE),
            )
            .count()
        )

    total = len(abandonados)
    return {
        'dias': dias,
        'abandonados': total,
        'valor_abandonado': float(valor_abandonado),
        'ticket_medio': float(valor_abandonado / total) if total else 0.0,
        'mensagens_enviadas': mensagens,
        'recuperados': recuperados,
        'valor_recuperado': float(valor_recuperado),
        'taxa_de_recuperacao': round(recuperados / total * 100, 1) if total else 0,
        'oportunidade_perdida': float(valor_abandonado - valor_recuperado),
        'sem_telefone': sem_telefone,
    }
