#!/usr/bin/env python3
"""Prova de ponta a ponta da Alelo no SANDBOX da Cielo. Não toca em produção.

    python3 scripts/cielo_sandbox_smoke.py

Usa as credenciais PÚBLICAS de sandbox que a própria Cielo publica na
documentação do Silent Order Post, e o cartão de exemplo da página da Alelo.
Faz o caminho inteiro que o checkout faz:

  1. OAuth do SOP              (servidor)
  2. AccessToken do SOP        (servidor)
  3. cartão -> PaymentToken    (é o que o NAVEGADOR faz; aqui simulado)
  4. venda com o token         (servidor) — DebitCard + Brand Elo, sem 3DS
  5. consulta por MerchantOrderId
  6. cancelamento total

O que este script responde e os testes unitários não conseguem:
  - a venda aceita `DebitCard.PaymentToken` junto de `Brand: "Elo"`?
  - o cartão tokeniza no host 'braspag' (pagador.com.br) ou no 'cielo'?
"""
import importlib.util
import pathlib
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace

import requests

RAIZ = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    'cielo_ecommerce', RAIZ / 'apps/stores/services/cielo_ecommerce.py')
cielo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cielo)

# Credenciais públicas da doc (docs.cielo.com.br/ecommerce-cielo/docs/integrando-com-o-sop).
MERCHANT_ID = '832ce400-9c97-4fe7-9d4f-0928675e36cd'
MERCHANT_KEY = 'IIHc5F35mO9BS1FQ64ZGaqqYPG9L1OvMh2ld8kYv'
SOP_CLIENT_ID = '6631016d-72e6-4db1-a2d2-9cbe61464925'
SOP_CLIENT_SECRET = 'flY1vN/dDx/5A9g/shJoOlTEiZfb9bZrig/WtJojqMM='
# Cartão de exemplo da página da Alelo.
CARTAO = dict(HolderName='Comprador Alelo', RawNumber='5080540487508044',
              Expiration='12/2035', SecurityCode='333', CardType='debitCard')

DESTINOS_DO_CARTAO = {
    'braspag': 'https://transactionsandbox.pagador.com.br/post/api/public/v1/card',
    'cielo': 'https://transactionsandbox.cieloecommerce.cielo.com.br/post/api/public/v1/card',
}


def passo(n, texto):
    print(f'\n[{n}] {texto}')


def main():
    passo(1, 'OAuth do SOP')
    r = requests.post(cielo._SOP_OAUTH[True], data={'grant_type': 'client_credentials'},
                      auth=(SOP_CLIENT_ID, SOP_CLIENT_SECRET), timeout=20)
    print('   HTTP', r.status_code)
    bearer = r.json().get('access_token')
    if not bearer:
        sys.exit(f'   FALHOU: {r.text[:300]}')

    def access_token():
        r = requests.post(cielo._SOP_ACCESSTOKEN[True], timeout=20, headers={
            'Content-Type': 'application/json', 'MerchantId': MERCHANT_ID,
            'Authorization': f'Bearer {bearer}'})
        return r.status_code, (r.json() or {}).get('AccessToken')

    payment_token = None
    for provider, url in DESTINOS_DO_CARTAO.items():
        passo(2, f'AccessToken do SOP (para testar o destino {provider!r})')
        status, token = access_token()
        print('   HTTP', status, '— token', 'ok' if token else 'AUSENTE')
        if not token:
            continue
        passo(3, f'cartão -> PaymentToken em {provider!r}')
        r = requests.post(url, data={**CARTAO, 'AccessToken': token}, timeout=20,
                          headers={'Accept': 'application/json'})
        print('   HTTP', r.status_code, r.text[:200])
        try:
            payment_token = r.json().get('PaymentToken')
        except ValueError:
            payment_token = None
        if payment_token:
            esperado = cielo.SOP_PROVIDER
            print(f'   >>> o destino que funciona é {provider!r} '
                  f'(o código está com {esperado!r}: {"OK" if provider == esperado else "TROCAR SOP_PROVIDER"})')
            break
    if not payment_token:
        sys.exit('\nFALHOU: nenhum destino devolveu PaymentToken.')

    pedido = SimpleNamespace(id=uuid.uuid4(), total=Decimal('0.50'))
    passo(4, 'venda com o token (DebitCard + Brand Elo, sem 3DS)')
    corpo = cielo.build_sale_payload(pedido, payment_token=payment_token,
                                     holder_name='Comprador Alelo',
                                     holder_document='11225468954')
    status, resposta = cielo.criar_venda(MERCHANT_ID, MERCHANT_KEY, corpo, sandbox=True)
    ok, estado, payment_id, motivo = cielo.interpret(status, resposta)
    print('   HTTP', status, '->', estado, '|', motivo, '| PaymentId', payment_id)
    if isinstance(resposta, dict):
        p = resposta.get('Payment') or {}
        print('   Status', p.get('Status'), 'ReturnCode', p.get('ReturnCode'),
              'Provider', p.get('Provider'), 'CapturedAmount', p.get('CapturedAmount'))
    else:
        print('  ', resposta)
    if estado != 'approved':
        sys.exit('\nFALHOU: a venda não foi aprovada. Veja o corpo acima.')

    passo(5, 'consulta por MerchantOrderId (o resgate de quando a resposta se perde)')
    status, achadas = cielo.consultar_por_pedido(
        MERCHANT_ID, MERCHANT_KEY, cielo.merchant_order_id(pedido), sandbox=True)
    print('   HTTP', status, achadas)

    passo(6, 'cancelamento total')
    status, cancel = cielo.cancelar(MERCHANT_ID, MERCHANT_KEY, payment_id, pedido.total, sandbox=True)
    print('   HTTP', status, cancel if not isinstance(cancel, dict) else
          {k: cancel.get(k) for k in ('Status', 'ReturnCode', 'ReturnMessage')})

    print('\nTUDO CERTO: a Alelo passa de ponta a ponta no sandbox.')


if __name__ == '__main__':
    main()
