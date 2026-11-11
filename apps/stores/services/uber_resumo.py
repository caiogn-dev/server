"""Uber Direct × frete cobrado, por faixa de km.

P75 e não média: com a média, metade das entregas custa mais do que ela.
O P75 cobre 3 de cada 4.
"""
from decimal import ROUND_HALF_UP, Decimal

FAIXAS = [(0, 3), (3, 5), (5, 7), (7, 10), (10, 999)]


def _rotulo(ini, fim):
    return f'{ini}+ km' if fim == 999 else f'{ini}–{fim} km'


def _q(v) -> Decimal:
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _percentil(valores, p):
    """Interpolação linear (igual ao numpy/Excel PERCENTIL.INC)."""
    v = sorted(valores)
    if not v:
        return None
    pos = (len(v) - 1) * p
    baixo = int(pos)
    alto = min(baixo + 1, len(v) - 1)
    return v[baixo] + (v[alto] - v[baixo]) * Decimal(str(pos - baixo))


def resumo_por_faixa(cotacoes):
    linhas = list(
        cotacoes.filter(fee__isnull=False, distancia_km__isnull=False)
        .values_list('distancia_km', 'fee', 'taxa_cobrada')
    )
    saida = []
    for ini, fim in FAIXAS:
        grupo = [(f, t) for km, f, t in linhas if ini <= km < fim]
        if not grupo:
            continue
        fees = [f for f, _ in grupo]
        cobradas = [t for _, t in grupo if t is not None]
        saida.append({
            'faixa': _rotulo(ini, fim),
            'n': len(grupo),
            'media_uber': _q(sum(fees) / len(fees)),
            'p75_uber': _q(_percentil(fees, 0.75)),
            'min_uber': _q(min(fees)),
            'max_uber': _q(max(fees)),
            'media_cobrada': _q(sum(cobradas) / len(cobradas)) if cobradas else None,
            'no_prejuizo': sum(1 for f, t in grupo if t is not None and f > t),
            'saldo': _q(sum((t or 0) - f for f, t in grupo)),
        })
    return saida
