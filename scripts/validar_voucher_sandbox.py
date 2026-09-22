"""Prova de ponta a ponta contra o SANDBOX do Pagar.me.

Nao e teste automatizado: fala com a rede de proposito. Roda a mao.

    python scripts/validar_voucher_sandbox.py

POR QUE ESTE ARQUIVO GANHOU ASSERCOES DE CHAVE

A primeira versao imprimia "RECUSA ESPERADA" e dava a impressao de ter
passado. Em 22/09 a leitura crua mostrou outra coisa:

    HTTP 404 -> ok=False  motivo cru: 'Token not found.'

Nos DOIS cenarios, inclusive no de aprovacao. A causa era o par de chaves:
secret de TESTE (`sk_test_...`) com public de PRODUCAO (`pk_V5kKl...`). O
token nasce no ambiente da public e e cobrado no ambiente da secret; ambientes
diferentes, token inexistente. Um trilho que nunca aprovou parecia um trilho
que recusava direitinho.

Recusa e 404 de token sao coisas opostas — uma e o sistema funcionando, a
outra e ele nem chegar na adquirente. O script agora separa as duas.
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

#: Cartoes do simulador de voucher do Pagar.me e o que cada um deve devolver.
#: Fonte: docs.pagar.me — "Simulador de Voucher".
#: `pending` e o ambiente dizendo "a adquirente responde depois": quem fecha o
#: caso e o webhook, nao esta chamada. Por isso 36 e 44 esperam a MESMA coisa
#: aqui e so divergem la na frente.
CENARIOS = (
    ('4000000000000010', 'approved', 'sucesso direto'),
    ('4000000000000028', 'failed',   'nao autorizada'),
    ('4000000000000036', 'pending',  'processing -> sucesso (fecha no webhook)'),
    ('4000000000000044', 'pending',  'processing -> falha (fecha no webhook)'),
)


def credenciais():
    vals = {}
    for linha in ENV.read_text().splitlines():
        if '=' in linha and not linha.strip().startswith('#'):
            chave, _, valor = linha.partition('=')
            vals[chave.strip()] = valor.strip()
    return vals


def exigir_par_de_teste(secret, public):
    """Aborta antes de gastar chamada se as chaves forem de ambientes diferentes.

    Cobrar de verdade com a secret de producao e o risco que justifica parar
    aqui, e nao depois de sete orders criadas.
    """
    s, p = '_test_' in secret, '_test_' in public
    print(f'secret de teste: {s}   public de teste: {p}')
    if s == p:
        return
    raise SystemExit(
        '\nABORTADO: par de chaves misturado.\n'
        f'  secret={secret[:12]}... ({"teste" if s else "PRODUCAO"})\n'
        f'  public={public[:12]}...  ({"teste" if p else "PRODUCAO"})\n'
        'O token nasce no ambiente da public e e cobrado no da secret. '
        'Misturados, toda cobranca volta 404 "Token not found" — que NAO e '
        'recusa, e a chamada nem chegando na adquirente.\n'
        'Pegue as duas chaves do MESMO ambiente no painel do Pagar.me.'
    )


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


def cobrar(secret, public, numero, esperado, rotulo):
    print(f'\n--- {rotulo} (cartao {numero}) ---')
    token = tokenizar(public, numero)
    print(f'  token: {token[:14]}...')

    payload = pagarme_orders.build_voucher_payload(
        pedido(), card_token=token, brand='vr',
        holder_name='ANA SILVA', holder_document='39053344705',
    )
    itens = payload['items']
    valor = payload['payments'][0]['amount']
    print(f'  amount: {valor}  |  soma(itens): {pagarme_orders.soma_dos_itens(itens)}')
    assert valor == pagarme_orders.soma_dos_itens(itens), 'INVARIANTE QUEBRADA'

    code, corpo = pagarme_orders.create_order(secret, payload)
    ok, status, oid, motivo = pagarme_orders.interpret(code, corpo)
    print(f'  HTTP {code} -> ok={ok} status={status} id={oid}')
    if motivo:
        print(f'  motivo cru : {motivo!r}')
        print(f'  para a tela: {pagarme_orders.mensagem_de_recusa(motivo)}')

    # 404 de token nunca e resultado de teste: e o teste nao tendo acontecido.
    if code == 404 and 'token' in str(motivo).lower():
        raise SystemExit('  ABORTADO: token nao existe no ambiente da secret. '
                         'Par de chaves misturado.')

    veredito = 'OK' if status == esperado else f'DIVERGIU (esperado {esperado})'
    print(f'  veredito: {veredito}')
    return status == esperado


def main():
    v = credenciais()
    secret, public = v['PAGARME_SECRET_KEY'], v['PAGARME_PUBLIC_KEY']
    exigir_par_de_teste(secret, public)

    resultados = [cobrar(secret, public, num, esp, rot) for num, esp, rot in CENARIOS]
    print(f'\n===== {sum(resultados)}/{len(resultados)} cenarios conforme o esperado =====')
    raise SystemExit(0 if all(resultados) else 1)


if __name__ == '__main__':
    main()
