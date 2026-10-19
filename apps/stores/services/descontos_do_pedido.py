"""De ONDE veio o desconto do pedido, em linhas: cupom, resgate, cashback.

19/10, dono: "não consigo ver qual cupom foi utilizado pelo cliente na
comanda", e o resgate da fidelidade aparecia só como "Desconto". O pedido
guarda um `discount` SOMADO (checkout_service: cupom + grátis + cashback);
as partes estão espalhadas em `coupon_code`, `metadata.loyalty_reward` e
`metadata.cashback_aplicado`. Painel, comanda do painel e print agent leem
daqui — uma regra, três telas.

O cupom não tem valor gravado à parte: é o que sobra do `discount` depois do
resgate e do cashback. Quando a conta não fecha (alguém editou o desconto à
mão para menos que as partes), nada é inventado: sai uma linha "Desconto" com
o total, que é o único número certo.
"""
from decimal import Decimal, InvalidOperation

_CENTAVO = Decimal('0.01')


def _dec(valor) -> Decimal:
    try:
        return Decimal(str(valor or 0)).quantize(_CENTAVO)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def _item_resgatado(order, valor: Decimal) -> str:
    """Nome da salada que saiu grátis: o item com o preço exato do resgate.

    O checkout dá de graça a salada qualificante mais barata, e grava só o
    valor — o item com aquele preço unitário é ela.
    """
    for item in order.items.all():
        if _dec(item.unit_price) == valor:
            return item.product_name
    return ''


def descontos_do_pedido(order) -> list[dict]:
    total = _dec(getattr(order, 'discount', 0))
    if total <= 0:
        return []

    metadata = getattr(order, 'metadata', None) or {}
    linhas = []

    resgate = metadata.get('loyalty_reward') or {}
    fidelidade = _dec(resgate.get('discount')) if resgate.get('applied') else Decimal('0.00')
    cashback = _dec(metadata.get('cashback_aplicado'))

    restante = total - fidelidade - cashback
    if restante < 0:
        return [{'tipo': 'desconto', 'rotulo': 'Desconto', 'valor': str(total)}]

    codigo = (getattr(order, 'coupon_code', '') or '').strip()
    if restante > 0:
        if codigo:
            linhas.append({'tipo': 'cupom', 'rotulo': f'Cupom {codigo}', 'valor': str(restante), 'codigo': codigo})
        else:
            motivo = (getattr(order, 'manual_discount_reason', '') or '').strip()
            linhas.append({
                'tipo': 'manual',
                'rotulo': f'Desconto: {motivo}' if motivo else 'Desconto',
                'valor': str(restante),
            })

    if fidelidade > 0:
        linha = {'tipo': 'fidelidade', 'rotulo': 'Resgate fidelidade', 'valor': str(fidelidade)}
        item = _item_resgatado(order, fidelidade)
        if item:
            linha['item'] = item
        linhas.append(linha)

    if cashback > 0:
        linhas.append({'tipo': 'cashback', 'rotulo': 'Cashback usado', 'valor': str(cashback)})

    return linhas
