"""Estoque dos pratos escolhidos DENTRO de um combo.

O Combo Família da Agrião são 30 marmitas escolhidas pelo cliente; cada uma
sai do estoque daquele sabor. Antes, só o estoque do próprio combo mexia
(e quase nenhum combo controla estoque), então o sabor acabava no freezer e
seguia à venda.

Uma escolha é o UUID de um produto ou de uma variante, repetido tantas vezes
quantas o cliente pediu (`group_selections`). Só mexe em produto com
`track_stock`; com variante, o saldo é o da variante — igual à linha avulsa
no checkout.
"""
from __future__ import annotations

from collections import Counter

from django.db.models import F
from django.db.models.functions import Greatest

from apps.stores.models import StoreProduct, StoreProductVariant

# Marca no display_data do StoreOrderComboItem: o pedido nasceu com esta regra
# e a baixa foi feita. Pedido antigo não tem e não pode "devolver" o que
# nunca saiu.
MARCA = 'estoque_das_escolhas'


def _contar(group_selections) -> Counter:
    contagem: Counter = Counter()
    for ids in (group_selections or {}).values():
        for sid in (ids if isinstance(ids, list) else [ids]):
            if sid:
                contagem[str(sid)] += 1
    return contagem


def _resolver(contagem: Counter, multiplicador: int):
    """[(produto, variante|None, quantidade)] só do que controla estoque."""
    if not contagem:
        return []
    ids = list(contagem)
    variantes = {
        str(v.id): v
        for v in StoreProductVariant.objects.filter(id__in=ids).select_related('product')
    }
    produtos = {
        str(p.id): p
        for p in StoreProduct.objects.filter(id__in=[i for i in ids if i not in variantes])
    }
    linhas = []
    for sid, qtd in contagem.items():
        variante = variantes.get(sid)
        produto = variante.product if variante is not None else produtos.get(sid)
        if produto is None or not produto.track_stock:
            continue
        linhas.append((produto, variante, qtd * max(int(multiplicador or 1), 1)))
    return linhas


def validar_disponivel(group_selections, quantidade_de_combos: int) -> None:
    """ValueError com o nome do sabor quando não há estoque para a escolha."""
    for produto, variante, precisa in _resolver(_contar(group_selections), quantidade_de_combos):
        if produto.allow_backorder:
            continue
        saldo = variante.stock_quantity if variante is not None else produto.stock_quantity
        if saldo is None:
            continue
        if saldo < precisa:
            nome = f"{produto.name} {variante.name}".strip() if variante is not None else produto.name
            restam = max(saldo, 0)
            raise ValueError(
                f"{nome} esgotado." if restam == 0 else f"{nome}: restam só {restam}."
            )


def _mover(group_selections, quantidade_de_combos: int, sinal: int) -> bool:
    linhas = _resolver(_contar(group_selections), quantidade_de_combos)
    for produto, variante, qtd in linhas:
        if variante is not None:
            StoreProductVariant.objects.filter(id=variante.id).update(
                stock_quantity=F('stock_quantity') - sinal * qtd
            )
        elif sinal > 0:
            StoreProduct.objects.filter(id=produto.id).update(
                stock_quantity=F('stock_quantity') - qtd,
                sold_count=F('sold_count') + qtd,
            )
        else:
            StoreProduct.objects.filter(id=produto.id).update(
                stock_quantity=F('stock_quantity') + qtd,
                sold_count=Greatest(F('sold_count') - qtd, 0),
            )
    return any(v is None for _, v, _ in linhas)


def baixar(order_combo_item) -> bool:
    """Baixa as escolhas de um combo vendido. True se algum PRODUTO mudou
    (o cardápio cacheado do agente precisa ser invalidado)."""
    return _mover(order_combo_item.group_selections, order_combo_item.quantity, +1)


def devolver(order_combo_item) -> None:
    if (order_combo_item.display_data or {}).get(MARCA):
        _mover(order_combo_item.group_selections, order_combo_item.quantity, -1)


def baixar_de_novo(order_combo_item) -> None:
    if (order_combo_item.display_data or {}).get(MARCA):
        _mover(order_combo_item.group_selections, order_combo_item.quantity, +1)
