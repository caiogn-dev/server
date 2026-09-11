"""Formato de fio da API do Pagar.me v5 para pagamento com voucher (VR/VA).

Funções puras, sem Django e sem rede — no molde de `mp_orders.py`. Quem fala
com o mundo é `create_order`; o resto é montagem e leitura de dicionário.
"""
import re
from decimal import Decimal, ROUND_HALF_UP

#: A lista NAO mora aqui — mora no catalogo, que e o que o cardapio e o painel
#: recebem por API. Repetir os valores neste arquivo criaria a segunda copia.
from apps.stores.services.voucher import bandeiras

BASE_URL = 'https://api.pagar.me/core/v5'
ORDERS_URL = f'{BASE_URL}/orders'
TOKENS_URL = f'{BASE_URL}/tokens'


def centavos(valor) -> int:
    """Reais -> centavos inteiros. O Pagar.me só fala centavos.

    Passa por Decimal de propósito: `int(29.90 * 100)` dá 2989 em float.
    """
    return int(
        (Decimal(str(valor)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    )


def somente_digitos(texto) -> str:
    return re.sub(r'\D', '', str(texto or ''))


def soma_dos_itens(items) -> int:
    return sum(int(i['amount']) * int(i['quantity']) for i in items)


def build_items(order, total=None):
    """Itens do pedido em centavos, garantindo que a soma feche com o total.

    O Pagar.me recusa a order inteira quando sum(items) != amount. E o total do
    pedido carrega frete e desconto, que os produtos sozinhos nunca fecham.
    """
    alvo = centavos(total if total is not None else order.total)

    items = []
    for it in order.items.all():
        items.append({
            'amount': centavos(it.unit_price),
            'description': (it.product_name or 'Item')[:255],
            'quantity': int(it.quantity or 1),
        })

    if not items:
        return [{'amount': alvo, 'description': f'Pedido {order.order_number}', 'quantity': 1}]

    frete = centavos(getattr(order, 'delivery_fee', 0) or 0)
    if frete > 0:
        items.append({'amount': frete, 'description': 'Taxa de entrega', 'quantity': 1})

    if soma_dos_itens(items) != alvo:
        # Desconto (cupom/fidelidade) não tem item negativo na API. Item único
        # consolidado perde granularidade, mas fecha a conta — e uma order
        # recusada não tem granularidade nenhuma.
        return [{'amount': alvo, 'description': f'Pedido {order.order_number}', 'quantity': 1}]

    return items


def statement_descriptor(order) -> str:
    """Texto na fatura do cliente. O Pagar.me corta em 13 caracteres no voucher."""
    nome = getattr(getattr(order, 'store', None), 'name', '') or 'CARDAPIDEX'
    return re.sub(r'[^A-Za-z0-9 ]', '', nome).strip().upper()[:13] or 'CARDAPIDEX'


def build_voucher_payload(order, *, card_token, brand, holder_name,
                           holder_document, total=None):
    """Payload de `POST /orders` para uma cobrança de voucher.

    Tudo ou nada por construção: um único elemento em `payments`, com `amount`
    igual à soma dos itens. Não existe caminho aqui que gere pagamento parcial.
    """
    bandeira = (brand or '').strip().lower()
    if bandeira not in bandeiras.valores():
        raise ValueError(
            f'Bandeira de voucher não aceita: {bandeira!r}. '
            f'Aceitas: {", ".join(bandeiras.valores())}.'
        )

    items = build_items(order, total=total)
    valor = soma_dos_itens(items)

    return {
        'items': items,
        'customer': {
            'name': (holder_name or 'Cliente')[:64],
            'document': somente_digitos(holder_document),
            'type': 'individual',
        },
        'payments': [{
            'payment_method': 'voucher',
            'amount': valor,
            'voucher': {
                'card_token': card_token,
                'statement_descriptor': statement_descriptor(order),
                'card': {
                    'holder_name': (holder_name or 'Cliente')[:64],
                    'holder_document': somente_digitos(holder_document),
                    'brand': bandeira,
                },
            },
        }],
        'metadata': {'pedido': str(order.order_number)},
    }
