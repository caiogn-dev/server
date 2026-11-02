"""Catálogo ÚNICO das formas de pagamento que um pedido grava.

`StoreOrder.payment_method` é um CharField livre; cada tela tinha o próprio
dicionário de nomes e o vale aparecia cru ("voucher") no painel. Este módulo é
a fonte do backend: nome para gente e quem é pago na entrega.

01/10: `card_on_delivery` separa a maquininha do dinheiro. Antes os dois eram
`cash`, e o caixa esperava na gaveta o dinheiro que tinha ido para a maquininha.
"""

ROTULOS = {
    'pix': 'PIX',
    'card': 'Cartão',
    'credit_card': 'Cartão de crédito',
    'debit_card': 'Cartão de débito',
    'cash': 'Dinheiro',
    'card_on_delivery': 'Cartão na maquininha',
    'voucher': 'Vale-refeição',
    'voucher_link': 'Vale-refeição (link)',
    # 28/10: vale passado na maquininha na entrega (pedido do painel).
    'voucher_on_delivery': 'Vale na entrega',
    # 28/10: fiado ia como `cash` + nota e virava PAGO ao entregar.
    'fiado': 'Fiado (a receber)',
    'link': 'Link de pagamento',
    'bank_transfer': 'Transferência',
    'other': 'Outro',
    # 19/10: pedido de total zero (resgate da fidelidade) — CheckoutService.SEM_COBRANCA.
    'sem_cobranca': 'Sem cobrança',
}

#: Pago em mãos na entrega/retirada: nasce pendente e liquida ao entregar.
PAGOS_NA_ENTREGA = frozenset({'cash', 'card_on_delivery', 'voucher_on_delivery'})


def rotulo(metodo) -> str:
    valor = (metodo or '').strip()
    return ROTULOS.get(valor, valor or 'Não informado')
