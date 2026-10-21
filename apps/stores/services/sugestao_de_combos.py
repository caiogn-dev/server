"""Sugestão de combos pelo que os clientes JÁ compram juntos (do Prefiro).

Sem IA de propósito: "estes dois saíram juntos em 23 pedidos" é um fato que o
dono confere no histórico; um combo inventado por modelo é palpite. O preço
sugerido é a soma com 10% de desconto — ponto de partida, o dono ajusta.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

from django.utils import timezone

from apps.stores.metrics.definicoes import STATUS_SEM_RECEITA

#: Abaixo disto, "compram juntos" é coincidência.
MINIMO_DE_PEDIDOS = 3
DESCONTO_SUGERIDO = Decimal('0.10')


def sugestao_de_combos(store, dias: int = 60, limite: int = 5, agora=None) -> list[dict]:
    from apps.stores.models import StoreOrderItem, StoreProduct

    agora = agora or timezone.now()
    itens = (
        StoreOrderItem.objects
        .filter(order__store=store, order__created_at__gte=agora - timedelta(days=dias),
                product__isnull=False)
        .exclude(order__status__in=STATUS_SEM_RECEITA)
        .values_list('order_id', 'product_id')
    )
    por_pedido: dict = defaultdict(set)
    for pedido, produto in itens:
        por_pedido[pedido].add(produto)

    pares = Counter()
    for produtos in por_pedido.values():
        for par in combinations(sorted(produtos, key=str), 2):
            pares[par] += 1

    candidatos = [(par, n) for par, n in pares.most_common() if n >= MINIMO_DE_PEDIDOS]
    if not candidatos:
        return []
    ids = {pid for par, _ in candidatos for pid in par}
    # Só o que está à venda hoje; ingrediente do montador não vira combo.
    vivos = {
        p.id: p for p in StoreProduct.disponiveis(store).filter(id__in=ids)
        .exclude(tags__contains=['ingrediente'])
    }

    sugestoes = []
    for (a, b), n in candidatos:
        if a not in vivos or b not in vivos:
            continue
        pa, pb = vivos[a], vivos[b]
        soma = pa.preco_vigente() + pb.preco_vigente()
        sugestoes.append({
            'produtos': [{'id': str(p.id), 'nome': p.name, 'preco': float(p.preco_vigente())} for p in (pa, pb)],
            'pedidos_juntos': n,
            'preco_somado': float(soma),
            'preco_sugerido': float((soma * (1 - DESCONTO_SUGERIDO)).quantize(Decimal('0.10'), ROUND_HALF_UP)),
        })
        if len(sugestoes) >= limite:
            break
    return sugestoes
