"""Formato de fio da API E-commerce Cielo — hoje só para o vale Alelo.

No molde de `pagarme_orders.py`: montagem e leitura de dicionário são puras;
quem fala com o mundo são as funções de rede, que devolvem (status, corpo) e
nunca levantam por HTTP.

Regras da Alelo na Cielo (docs.cielo.com.br/ecommerce-cielo/docs/alelo):
- vai como `DebitCard` com `Brand: "Elo"` e `Authenticate: false` (sem 3DS);
- captura é automática — a resposta boa já vem `Status: 2`;
- cancelamento só do valor inteiro e só no mesmo dia (D0). Do D+1 em diante,
  só com a Alelo.

O número do cartão NUNCA passa por aqui. O navegador manda o cartão direto
para a Cielo pelo Silent Order Post e só o `PaymentToken` chega ao servidor.
"""
import logging
import re
import unicodedata
import uuid
from decimal import Decimal, ROUND_HALF_UP

import requests

logger = logging.getLogger(__name__)

_HOSTS = {
    True: ('https://apisandbox.cieloecommerce.cielo.com.br',
           'https://apiquerysandbox.cieloecommerce.cielo.com.br'),
    False: ('https://api.cieloecommerce.cielo.com.br',
            'https://apiquery.cieloecommerce.cielo.com.br'),
}

_SOP_OAUTH = {
    True: 'https://authsandbox.braspag.com.br/oauth2/token',
    False: 'https://auth.braspag.com.br/oauth2/token',
}
_SOP_ACCESSTOKEN = {
    True: 'https://transactionsandbox.pagador.com.br/post/api/public/v2/accesstoken',
    False: 'https://transaction.pagador.com.br/post/api/public/v2/accesstoken',
}
#: Um script só para os dois ambientes; quem escolhe é o parâmetro `environment`.
SOP_SCRIPT_URL = 'https://www.pagador.com.br/post/scripts/silentorderpost-1.0.min.js'
#: O script tem dois destinos para o cartão: 'braspag' (pagador.com.br) e
#: 'cielo' (cieloecommerce.cielo.com.br). O AccessToken sai de pagador.com.br
#: (doc atual da Cielo), então o cartão vai para o mesmo host. Vai do backend
#: para o cardápio para que trocar isto não exija deploy de frontend.
SOP_PROVIDER = 'braspag'

#: Status da transação de débito (reference/lista-de-status-da-transação-para-cartão-de-débito).
APROVADO = frozenset({2})
EM_VOO = frozenset({0, 1, 12})
DEVOLVIDO = frozenset({10, 11})


def urls(sandbox: bool):
    """(host transacional, host de consulta)."""
    return _HOSTS[bool(sandbox)]


def centavos(valor) -> int:
    return int((Decimal(str(valor)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _somente_digitos(texto) -> str:
    return re.sub(r'\D', '', str(texto or ''))


def _so_letras(texto) -> str:
    """`Customer.Name` aceita só a-z/A-Z. Translitera antes de filtrar, senão
    'Lúcia' vira 'Lcia'."""
    ascii_ = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z ]', '', ascii_)).strip()


def merchant_order_id(order) -> str:
    """Alfanumérico, até 50. O UUID do pedido sem traços — e é por ele que a
    venda é achada de novo quando a resposta se perde."""
    return re.sub(r'[^A-Za-z0-9]', '', str(order.id))[:50]


def build_sale_payload(order, *, payment_token, holder_name, holder_document, total=None):
    documento = _somente_digitos(holder_document)
    return {
        'MerchantOrderId': merchant_order_id(order),
        'Customer': {
            'Name': (_so_letras(holder_name) or 'Cliente')[:255],
            'Identity': documento,
            'IdentityType': 'CNPJ' if len(documento) == 14 else 'CPF',
        },
        'Payment': {
            'Type': 'DebitCard',
            'Authenticate': False,
            'Amount': centavos(total if total is not None else order.total),
            # `Brand` junto do token: a doc da Alelo exige "Elo" e a do SOP não
            # diz se o token dispensa. Mandar é o lado seguro.
            'DebitCard': {'PaymentToken': payment_token, 'Brand': 'Elo'},
        },
    }


def interpret(status_code, body):
    """Normaliza -> (ok, status, payment_id, motivo). Mesmo formato do Pagar.me."""
    if isinstance(body, list):
        # Erro de validação: [{"Code": 126, "Message": "..."}]
        motivo = '; '.join(str(e.get('Message') or e.get('Code') or '') for e in body if isinstance(e, dict))
        return False, 'failed', None, motivo or 'erro'

    body = body or {}
    pagamento = body.get('Payment') or {}
    payment_id = pagamento.get('PaymentId') or None
    motivo = str(pagamento.get('ReturnMessage') or '')

    if status_code not in (200, 201):
        return False, 'failed', payment_id, motivo or 'erro'

    try:
        codigo = int(pagamento.get('Status'))
    except (TypeError, ValueError):
        return False, 'failed', payment_id, motivo or 'sem status'

    if codigo in APROVADO:
        return True, 'approved', payment_id, motivo
    if codigo in EM_VOO:
        if codigo == 1:
            # Débito da Alelo é captura automática. Autorizado-sem-captura não
            # deveria existir; se aparecer, alguém precisa olhar.
            logger.error('[cielo] venda %s voltou Authorized (1) sem captura automática', payment_id)
        return True, 'pending', payment_id, motivo
    if codigo in DEVOLVIDO:
        return False, 'refunded', payment_id, motivo
    return False, 'failed', payment_id, motivo


#: ReturnCode do emissor -> o que o cliente faz. Códigos da tabela ABECS que a
#: Cielo repassa; o texto cru não diz ao cliente qual é a saída dele.
_RECUSAS = {
    '51': 'O seu vale não tem saldo para este valor. Use outro cartão ou pague no PIX.',
    '54': 'Este vale está vencido. Use outro cartão ou pague no PIX.',
    '57': 'Este vale está vencido. Use outro cartão ou pague no PIX.',
    '78': 'Este vale está bloqueado. Fale com a operadora do seu benefício ou pague no PIX.',
    '77': 'Este vale foi cancelado. Use outro cartão ou pague no PIX.',
    '14': 'Confira o número, a validade e o CVV do cartão do vale e tente de novo.',
    '82': 'Confira o número, a validade e o CVV do cartão do vale e tente de novo.',
    '55': 'Confira os dados do cartão do vale e tente de novo.',
    '58': 'Este vale não aceita compra pela internet. Use outro cartão ou pague no PIX.',
    '03': 'Esta loja ainda não aceita Alelo pela internet. Use outro cartão ou pague no PIX.',
}
RECUSA_GENERICA = 'O pagamento com vale não foi autorizado. Use outro cartão ou pague no PIX.'
FALHA_DE_REDE = (
    'Não conseguimos falar com a operadora do vale agora. '
    'Tente de novo em instantes ou pague no PIX.'
)


def mensagem_de_recusa(return_code, return_message='') -> str:
    return _RECUSAS.get(str(return_code or '').strip().zfill(2), RECUSA_GENERICA)


# ── rede ─────────────────────────────────────────────────────────────────────

def _headers(merchant_id, merchant_key):
    return {
        'Content-Type': 'application/json',
        'MerchantId': merchant_id,
        'MerchantKey': merchant_key,
        'RequestId': str(uuid.uuid4()),
    }


def _json(r):
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def criar_venda(merchant_id, merchant_key, payload, *, sandbox, timeout=25):
    transacional, _ = urls(sandbox)
    r = requests.post(f'{transacional}/1/sales/', json=payload,
                      headers=_headers(merchant_id, merchant_key), timeout=timeout)
    return _json(r)


def consultar_venda(merchant_id, merchant_key, payment_id, *, sandbox, timeout=15):
    _, consulta = urls(sandbox)
    r = requests.get(f'{consulta}/1/sales/{payment_id}',
                     headers=_headers(merchant_id, merchant_key), timeout=timeout)
    return _json(r)


def consultar_por_pedido(merchant_id, merchant_key, moid, *, sandbox, timeout=15):
    """Devolve {'Payments': [{'PaymentId': ...}]} — só os ids; o status exige
    `consultar_venda` em seguida."""
    _, consulta = urls(sandbox)
    r = requests.get(f'{consulta}/1/sales', params={'merchantOrderId': moid},
                     headers=_headers(merchant_id, merchant_key), timeout=timeout)
    return _json(r)


def cancelar(merchant_id, merchant_key, payment_id, valor, *, sandbox, timeout=25):
    """Estorno TOTAL. A Alelo não aceita parcial e só aceita no D0."""
    transacional, _ = urls(sandbox)
    r = requests.put(f'{transacional}/1/sales/{payment_id}/void',
                     params={'amount': centavos(valor)},
                     headers=_headers(merchant_id, merchant_key), timeout=timeout)
    return _json(r)


# ── Silent Order Post ────────────────────────────────────────────────────────

class SopIndisponivel(Exception):
    """Não deu para abrir o formulário seguro do cartão. O checkout mostra
    "pague de outro jeito" em vez de um 500."""


def _credencial_do_sop(gateway):
    client_id = str((getattr(gateway, 'configuration', None) or {}).get('sop_client_id') or '').strip()
    segredo = str(getattr(gateway, 'api_secret', '') or '').strip()
    return client_id, segredo


def sop_configurado(gateway) -> bool:
    """Sem isto o cardápio não tem como abrir o formulário do cartão — e a
    Alelo não pode ser anunciada como forma de pagamento."""
    return all(_credencial_do_sop(gateway)) and bool(getattr(gateway, 'public_key', ''))


def _bearer_do_sop(gateway):
    from django.core.cache import cache

    client_id, segredo = _credencial_do_sop(gateway)
    if not client_id or not segredo:
        raise SopIndisponivel('Loja sem Client ID/Secret do Silent Order Post.')

    chave = f'cielo:sop:bearer:{gateway.id}:{client_id}'
    guardado = cache.get(chave)
    if guardado:
        return guardado

    r = requests.post(
        _SOP_OAUTH[bool(gateway.is_sandbox)],
        data={'grant_type': 'client_credentials'},
        auth=(client_id, segredo), timeout=15,
    )
    status, corpo = _json(r)
    token = (corpo or {}).get('access_token') if isinstance(corpo, dict) else None
    if status not in (200, 201) or not token:
        raise SopIndisponivel(f'OAuth do SOP respondeu {status}.')
    # Margem de 60 s: não entregar ao navegador um bearer que morre no caminho.
    vida = max(int(corpo.get('expires_in') or 0) - 60, 0)
    if vida:
        cache.set(chave, token, vida)
    return token


def token_do_sop(gateway) -> str:
    """AccessToken do SOP — vale para UM cartão, por 20 min. Um por checkout."""
    try:
        bearer = _bearer_do_sop(gateway)
        r = requests.post(
            _SOP_ACCESSTOKEN[bool(gateway.is_sandbox)],
            headers={
                'Content-Type': 'application/json',
                'MerchantId': gateway.public_key,
                'Authorization': f'Bearer {bearer}',
            },
            timeout=15,
        )
    except requests.RequestException as erro:
        raise SopIndisponivel(f'SOP inacessível: {erro}') from erro

    status, corpo = _json(r)
    token = (corpo or {}).get('AccessToken') if isinstance(corpo, dict) else None
    if status not in (200, 201) or not token:
        raise SopIndisponivel(f'AccessToken do SOP respondeu {status}.')
    return token
