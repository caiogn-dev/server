"""Formato de fio da API do Pagar.me v5 para pagamento com voucher (VR/VA).

Funções puras, sem Django e sem rede — no molde de `mp_orders.py`. Quem fala
com o mundo é `create_order`; o resto é montagem e leitura de dicionário.
"""
import re
import unicodedata
import uuid
from decimal import Decimal, ROUND_HALF_UP

import requests

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


def email_aceito_pelo_gateway(email):
    """O e-mail limpo, se um gateway o aceitaria; senão string vazia.

    Irmã de `mp_orders.email_aceito_pelo_mp` — a regra é a mesma dos dois lados,
    e vive em cada módulo de gateway para nenhum deles depender do outro.
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    limpo = (email or '').strip()
    if not limpo:
        return ''
    try:
        validate_email(limpo)
    except ValidationError:
        return ''
    if limpo.rsplit('@', 1)[-1].lower().endswith(('.local', '.test', '.invalid')):
        return ''
    from apps.stores.services.checkout_service import is_placeholder_email
    if is_placeholder_email(limpo):
        return ''
    return limpo


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

    cliente = {
        'name': (holder_name or 'Cliente')[:64],
        'document': somente_digitos(holder_document),
        'type': 'individual',
    }
    # O Pagar.me cadastra o cliente por este bloco. E-mail inválido ou identidade
    # interna (`...@pastita.local`) não sai daqui — mesma regra do Mercado Pago,
    # onde um e-mail ruim derrubou a compra inteira (17/set).
    email = email_aceito_pelo_gateway(getattr(order, 'customer_email', ''))
    if email:
        cliente['email'] = email

    return {
        'items': items,
        'customer': cliente,
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


def _auth(secret_key):
    """Basic auth do Pagar.me: usuário = secret key, senha vazia."""
    return (secret_key, '')


def create_order(secret_key, payload, timeout=25):
    """POST /orders. Devolve (status_code, body) — nunca levanta por HTTP."""
    headers = {
        'Content-Type': 'application/json',
        'Idempotency-Key': str(uuid.uuid4()),
    }
    r = requests.post(
        ORDERS_URL, json=payload, headers=headers,
        auth=_auth(secret_key), timeout=timeout,
    )
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def consultar_order(secret_key, order_id, timeout=15):
    """GET /orders/{id} — a fonte da verdade quando o webhook chega."""
    r = requests.get(
        f'{ORDERS_URL}/{order_id}', auth=_auth(secret_key), timeout=timeout
    )
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def interpret(status_code, body):
    """Normaliza a resposta -> (ok, status, external_id, motivo).

    O motivo da recusa mora em `charges[0].last_transaction.acquirer_message`.
    O `message` do corpo de fora é genérico e não serve para a tela.
    """
    body = body or {}
    charges = body.get('charges') or []
    primeira = charges[0] if charges else {}
    transacao = primeira.get('last_transaction') or {}

    external_id = str(body.get('id')) if body.get('id') else None
    motivo = (
        transacao.get('acquirer_message')
        or primeira.get('status')
        or body.get('message')
        or ''
    )

    if status_code not in (200, 201):
        return False, 'failed', external_id, (motivo or 'erro')

    status_charge = (primeira.get('status') or body.get('status') or '').lower()
    if status_charge in ('paid', 'captured'):
        return True, 'approved', external_id, motivo
    if status_charge in ('pending', 'processing', 'waiting_payment', 'analyzing'):
        return True, 'pending', external_id, motivo
    if status_charge in ('refunded', 'chargedback'):
        # Dinheiro que ENTROU e voltou — não é o mesmo caso de nunca ter sido
        # autorizado. Cair no 'failed' de baixo faria o handler gravar uma
        # cobrança que teve sucesso como se tivesse falhado.
        return False, 'refunded', external_id, motivo
    return False, 'failed', external_id, motivo


#: Motivo do adquirente -> o que o cliente precisa fazer. O texto cru vem do
#: adquirente e não diz ao cliente qual é a saída dele.
MENSAGENS_DE_RECUSA = {
    'saldo insuficiente': 'O seu vale não tem saldo para este valor. Use outro cartão ou pague no PIX.',
    'cartao expirado': 'Este vale está vencido. Use outro cartão ou pague no PIX.',
    'cartao invalido': 'Confira os dados do cartão do vale e tente de novo.',
    'senha invalida': 'Confira os dados do cartão do vale e tente de novo.',
    'transacao nao permitida': 'Este vale não aceita compra pela internet. Use outro cartão ou pague no PIX.',
    'estabelecimento invalido': 'Esta loja ainda não aceita esta bandeira de vale. Use outro cartão ou pague no PIX.',
    'cartao bloqueado': 'Este vale está bloqueado. Fale com a operadora do seu benefício ou pague no PIX.',
    # Código 1011 do adquirente. Era a ÚNICA recusa já vista em produção
    # (7 de 7 orders, medido em 22/09) e caía na genérica, que manda
    # trocar de cartão — conselho errado para um dígito digitado torto.
    'verifique os dados do cartao': 'Confira o número, a validade e o CVV do cartão do vale e tente de novo.',
}

RECUSA_GENERICA = 'O pagamento com vale não foi autorizado. Use outro cartão ou pague no PIX.'


def mensagem_de_recusa(motivo) -> str:
    """Motivo em português, pronto para a tela — sem vazar código técnico.

    Transliterar antes de filtrar: sem isso, "Cartão" vira "carto" e nunca
    bate com a chave do dicionário — 6 das 7 mensagens específicas caindo
    caladas na genérica. Mesmo padrão de `mp_orders.statement_descriptor`.
    """
    texto = unicodedata.normalize('NFKD', str(motivo or ''))
    texto = texto.encode('ascii', 'ignore').decode('ascii').strip().lower()
    chave = re.sub(r'\s+', ' ', re.sub(r'[^a-z ]', '', texto)).strip()
    return MENSAGENS_DE_RECUSA.get(chave, RECUSA_GENERICA)
