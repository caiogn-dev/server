"""Desconto para quem RETIRA no balcão (ex.: Black Friday 26/11 na Cê: 20%).

    store.metadata['desconto_retirada'] = {
        'ativo': True,
        'percentual': 20,                         # sobre o subtotal já com cupom
        'inicio': '2026-11-26T00:00:00-03:00',    # opcional
        'fim': '2026-11-26T23:59:59-03:00',       # opcional
    }

O cardápio soma igual (totalDoPedido): mesma base, mesmo arredondamento.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.stores.services.frete_promocional import _dentro_da_janela

_CENTAVO = Decimal('0.01')


def _promocao(store):
    promo = (getattr(store, 'metadata', None) or {}).get('desconto_retirada') or {}
    if not isinstance(promo, dict) or not promo.get('ativo'):
        return None
    try:
        percentual = Decimal(str(promo.get('percentual') or 0))
    except (InvalidOperation, ValueError):
        return None
    if percentual <= 0 or percentual > 100 or not _dentro_da_janela(promo):
        return None
    return percentual


def desconto_da_retirada(store, base, metodo) -> Decimal:
    """Quanto sai do pedido de retirada; 0 para entrega ou sem promoção."""
    percentual = _promocao(store)
    if percentual is None or metodo != 'pickup':
        return Decimal('0')
    base = max(Decimal(str(base or 0)), Decimal('0'))
    return (base * percentual / 100).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def promocao_para_vitrine(store):
    percentual = _promocao(store)
    return {'percentual': float(percentual)} if percentual is not None else None
