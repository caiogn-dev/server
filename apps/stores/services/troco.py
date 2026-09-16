"""Troco do pagamento em dinheiro.

Valores guardados em `StoreOrder.change_for`:
- `None` = ninguém perguntou (PDV, bot, pedido que não é em dinheiro);
- `0`    = o cliente disse que não precisa de troco;
- `> 0`  = "troco para" este valor, que nunca fica abaixo do total.

🚨 Dado ruim NUNCA derruba a venda. O cardápio já barra troco menor que o
total antes de enviar; se algo escapar (app velho, bot, payload na mão), o
troco é descartado e o pedido segue. O pior caso é o entregador perguntar na
porta, que é exatamente como era antes deste campo existir.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

logger = logging.getLogger(__name__)

_CENTAVOS = Decimal('0.01')
# Ninguém pede troco para R$ 5 mil numa entrega de comida. Valor assim é
# digitação errada (um zero a mais) e imprimir "LEVAR R$ 9.965" confunde mais
# do que não imprimir nada.
TETO = Decimal('5000.00')


def _decimal(valor) -> Decimal | None:
    # bool é int em Python: `True` viraria "troco para R$ 1".
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float, Decimal)):
        texto = str(valor)
    elif isinstance(valor, str):
        texto = valor.strip().replace('R$', '').strip().replace(',', '.')
    else:
        return None
    if not texto:
        return None
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite():
        return None
    return numero


def troco_informado(valor, total, payment_method: str) -> Decimal | None:
    """O troco que vale gravar no pedido, ou `None` para descartar."""
    if (payment_method or '').strip().lower() != 'cash':
        return None
    numero = _decimal(valor)
    if numero is None:
        return None
    if numero == 0:
        return Decimal('0')
    total = Decimal(total or 0)
    if numero < 0 or numero < total or numero > TETO:
        logger.warning('troco descartado: valor=%r total=%s', valor, total)
        return None
    return numero.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def troco_a_levar(change_for, total) -> Decimal | None:
    """Quanto o entregador leva de troco. `None` quando ninguém informou."""
    if change_for is None:
        return None
    change_for = Decimal(change_for)
    if change_for == 0:
        return Decimal('0')
    return max(Decimal('0'), change_for - Decimal(total or 0)).quantize(_CENTAVOS)
