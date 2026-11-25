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


# ── Formas que o CARDÁPIO oferece, com interruptor do lojista (25/11) ──────────
#
# O cardápio oferecia tudo que estava conectado e o dono só tirava uma forma
# desconectando o gateway. `metadata.formas_desligadas` guarda as que ele tirou;
# vale para a config pública E para o checkout (que recusa).

CHAVE_FORMAS_DESLIGADAS = 'formas_desligadas'

#: Ordem da tela do painel e nome que o lojista lê.
FORMAS_DO_CARDAPIO = (
    ('pix', 'PIX'),
    ('credit_card', 'Cartão online'),
    ('cash', 'Dinheiro na entrega ou retirada'),
    ('card_on_delivery', 'Maquininha na entrega ou retirada'),
    ('voucher', 'Vale-refeição no cardápio'),
    ('voucher_link', 'Vale-refeição por link'),
)

_SINONIMOS = {'card': 'credit_card', 'debit_card': 'credit_card'}


def _canonica(metodo) -> str:
    valor = (metodo or '').strip()
    return _SINONIMOS.get(valor, valor)


def formas_desligadas(store) -> set:
    metadata = getattr(store, 'metadata', None)
    lista = metadata.get(CHAVE_FORMAS_DESLIGADAS) if isinstance(metadata, dict) else None
    return {_canonica(m) for m in (lista or []) if isinstance(m, str)}


def forma_desligada(store, metodo) -> bool:
    return _canonica(metodo) in formas_desligadas(store)
