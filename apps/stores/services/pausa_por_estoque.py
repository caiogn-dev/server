"""Pausa automática ao zerar o estoque (opt-in por produto: `pausar_ao_zerar`).

Os decrementos de estoque usam `.update(F(...))`, que não dispara signal — por
isso o checkout, o PDV e o bot chamam `pausar_se_zerou` depois da baixa, e o
cancelamento chama `retomar_se_repos`. Salvar o produto pelo painel passa pelo
signal de `save`. Só mexe em quem tem a flag ligada; produto que o dono
desativou à mão (`inactive`) nunca volta sozinho.
"""
from django.db.models import Q


def pausar_se_zerou(product_ids) -> int:
    from apps.stores.models import StoreProduct

    ids = [i for i in (product_ids or []) if i]
    if not ids:
        return 0
    return StoreProduct.objects.filter(
        id__in=ids, pausar_ao_zerar=True, track_stock=True, allow_backorder=False,
        stock_quantity__lte=0, status=StoreProduct.ProductStatus.ACTIVE,
    ).update(status=StoreProduct.ProductStatus.OUT_OF_STOCK)


def retomar_se_repos(product_ids) -> int:
    from apps.stores.models import StoreProduct

    ids = [i for i in (product_ids or []) if i]
    if not ids:
        return 0
    return StoreProduct.objects.filter(
        id__in=ids, pausar_ao_zerar=True, stock_quantity__gt=0,
        status=StoreProduct.ProductStatus.OUT_OF_STOCK,
    ).update(status=StoreProduct.ProductStatus.ACTIVE)
