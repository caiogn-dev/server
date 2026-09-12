"""Prova de ponta a ponta contra o SANDBOX do Pagar.me.

Nao e teste automatizado: fala com a rede de proposito. Roda a mao.

    python scripts/validar_voucher_sandbox.py
"""
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, '/app')

import os, django  # noqa: E402
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()

from apps.stores.services import pagarme_orders  # noqa: E402

ENV = Path(os.environ.get('PAGARME_ENV_FILE', '/home/graco/WORK/.env.pagarme.local'))


def credenciais():
    vals = {}
    for linha in ENV.read_text().splitlines():
        if '=' in linha and not linha.strip().startswith('#'):
            chave, _, valor = linha.partition('=')
            vals[chave.strip()] = valor.strip()
    return vals


def tokenizar(public_key, numero, cvv='351'):
    import requests
    r = requests.post(
        f'{pagarme_orders.TOKENS_URL}?appId={public_key}',
        json={'type': 'card', 'card': {
            'number': numero, 'holder_name': 'ANA SILVA',
            'exp_month': 1, 'exp_year': 30, 'cvv': cvv,
        }},
        timeout=25,
    )
    if r.status_code not in (200, 201):
        raise SystemExit(f'Tokenizacao falhou ({r.status_code}): {r.text[:300]}')
    return r.json()['id']


def pedido(total='25.00'):
    return SimpleNamespace(
        order_number='SANDBOX-1', total=Decimal(total),
        delivery_fee=Decimal('0.00'), store=SimpleNamespace(name='Ce Saladas'),
        items=SimpleNamespace(all=lambda: [SimpleNamespace(
            product_name='Salada Cesar', unit_price=Decimal(total), quantity=1)]),
    )


def cobrar(secret, public, numero, rotulo):
    print(f'\n--- {rotulo} (cartao {numero}) ---')
    token = tokenizar(public, numero)
    print(f'  token: {token[:14]}...')

    payload = pagarme_orders.build_voucher_payload(
        pedido(), card_token=token, brand='vr',
        holder_name='ANA SILVA', holder_document='39053344705',
    )
    itens = payload['items']
    valor = payload['payments'][0]['amount']
    print(f'  itens: {itens}')
    print(f'  amount: {valor}  |  soma(itens): {pagarme_orders.soma_dos_itens(itens)}')
    assert valor == pagarme_orders.soma_dos_itens(itens), 'INVARIANTE QUEBRADA'

    code, corpo = pagarme_orders.create_order(secret, payload)
    ok, status, oid, motivo = pagarme_orders.interpret(code, corpo)
    print(f'  HTTP {code} -> ok={ok} status={status} id={oid}')
    if motivo:
        print(f'  motivo cru : {motivo!r}')
        print(f'  para a tela: {pagarme_orders.mensagem_de_recusa(motivo)}')
    if oid:
        c2, consultado = pagarme_orders.consultar_order(secret, oid)
        print(f'  re-fetch HTTP {c2} -> status {pagarme_orders.interpret(c2, consultado)[1]}')
    return ok, status, corpo


def main():
    v = credenciais()
    secret, public = v['PAGARME_SECRET_KEY'], v['PAGARME_PUBLIC_KEY']
    print(f'secret _test_: {"_test_" in secret}   public _test_: {"_test_" in public}')
    print('(o nome nao decide nada — o que decide e a resposta da API)')

    cobrar(secret, public, '4000000000000010', 'APROVACAO ESPERADA')
    cobrar(secret, public, '4000000000000028', 'RECUSA ESPERADA')


if __name__ == '__main__':
    main()
