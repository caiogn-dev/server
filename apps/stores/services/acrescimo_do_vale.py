"""Acréscimo cobrado do cliente quando ele paga com vale — FONTE ÚNICA.

POR QUE EXISTE. Receber em vale custa caro: a operadora fica com uma fatia que
não existe no PIX nem no dinheiro. Quem escolhe pagar assim paga esse custo —
não a loja, e não os outros clientes através do preço do prato.

A Lei 13.455/2017 permite preço diferente por meio de pagamento. O que ela
exige é INFORMAÇÃO: o acréscimo tem que estar visível ANTES de o cliente
confirmar, nunca como surpresa na tela de pagar. Por isso o percentual sai na
configuração pública da loja, e a tela mostra a linha no instante em que ele
marca o vale.

VALE PARA OS DOIS CAMINHOS. `voucher` (cobrado pelo Pagar.me) e `voucher_link`
(Vólus, cobrada por QR) são o mesmo negócio para o cliente: ele está pagando
com vale-alimentação. Um `if` que cobrisse só um deles seria a diferença
aparecendo na conta de quem escolheu a bandeira "errada".

ARREDONDA PARA BAIXO, como a comissão do Mercado Pago: cobrar centavo a mais do
que o combinado é o erro caro quando o número é um percentual anunciado.
"""
from decimal import ROUND_DOWN, Decimal

#: Meios de pagamento que são "vale" para o cliente, independentemente de como
#: a cobrança acontece nos bastidores.
MEIOS_DE_VALE = ('voucher', 'voucher_link')

CHAVE_DO_PERCENTUAL = 'voucher_fee_percent'


def e_pagamento_com_vale(payment_method) -> bool:
    return str(payment_method or '').strip().lower() in MEIOS_DE_VALE


def percentual_do_vale(store) -> Decimal:
    """Quanto esta loja acrescenta, em %. Zero = desligado (o padrão).

    Mora no `metadata` da loja e não numa variável de ambiente porque é um
    número de NEGÓCIO por loja: cliente novo pode entrar com percentual
    diferente do antigo sem deploy.
    """
    metadata = getattr(store, 'metadata', None) or {}
    if not isinstance(metadata, dict):
        return Decimal('0')
    bruto = metadata.get(CHAVE_DO_PERCENTUAL)
    if bruto in (None, ''):
        return Decimal('0')
    try:
        percentual = Decimal(str(bruto).replace(',', '.'))
    except Exception:
        return Decimal('0')
    # Percentual negativo viraria DESCONTO por pagar com vale, que é o oposto
    # do que este módulo existe para fazer. E acima de 100 é dedo trocado.
    if percentual <= 0 or percentual > 100:
        return Decimal('0')
    return percentual


def acrescimo_do_vale(store, base, payment_method) -> Decimal:
    """O acréscimo em reais. Zero quando não é vale ou a loja não cobra.

    `base` é o valor sobre o qual o percentual incide — subtotal + frete −
    desconto, ou seja, o que o cliente pagaria sem o acréscimo. Incidir sobre o
    subtotal puro cobraria a mais de quem usou cupom.
    """
    if not e_pagamento_com_vale(payment_method):
        return Decimal('0.00')
    percentual = percentual_do_vale(store)
    if percentual <= 0:
        return Decimal('0.00')
    valor = Decimal(str(base or 0))
    if valor <= 0:
        return Decimal('0.00')
    return (valor * percentual / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_DOWN,
    )
