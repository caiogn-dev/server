"""Quanto ficou em carrinhos que não viraram pedido.

Fonte: `StoreCart` — todo produto posto na sacola do site/app cria (ou
atualiza) um carrinho no servidor, ligado ao navegador (`session_key`) ou ao
login (`user`). Quando vira pedido, `create_order` esvazia e desativa o
carrinho; então o que sobra ativo e com itens é carrinho que ninguém fechou.

Abandonado = ativo, com itens, parado entre 1 hora (antes disso a pessoa pode
estar escolhendo) e `dias` dias.
"""
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

LEMBRETES = ('reminder_30min_sent', 'reminder_2h_sent', 'reminder_24h_sent')


def resumo(loja, dias: int = 7, agora=None) -> dict:
    from apps.stores.models import StoreCart

    agora = agora or timezone.now()
    carrinhos = (
        StoreCart.objects
        .filter(
            store=loja, is_active=True,
            updated_at__gte=agora - timedelta(days=dias),
            updated_at__lte=agora - timedelta(hours=1),
        )
        .prefetch_related('items__product', 'items__variant', 'combo_items')
    )
    total = Decimal('0')
    quantos = identificados = com_lembrete = 0
    produtos = Counter()
    for carrinho in carrinhos:
        itens = list(carrinho.items.all())
        if not itens and not carrinho.combo_items.exists():
            continue
        quantos += 1
        total += Decimal(str(carrinho.subtotal or 0))
        if carrinho.user_id:
            identificados += 1
        if any((carrinho.metadata or {}).get(k) for k in LEMBRETES):
            com_lembrete += 1
        for nome in {i.product.name for i in itens if i.product_id}:
            produtos[nome] += 1
    return {
        'dias': dias,
        'carrinhos': quantos,
        'valor_total': float(total.quantize(Decimal('0.01'))),
        'identificados': identificados,
        'com_lembrete': com_lembrete,
        'produtos': [
            {'nome': nome, 'carrinhos': n}
            for nome, n in sorted(produtos.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        ],
    }
