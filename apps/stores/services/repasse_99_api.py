"""Repasse da 99Food pela API financeira — conciliação diária sem o dono copiar nada.

Contrato (developer-food.99app.com › Food › Financial API, lido em 06/11/2026):
- Token próprio, do APP (não da loja): POST /v3/auth/authtoken/signIn
  {retailer: app_id, secret: app_secret} → {accessToken, expiresIn (s, ~6 h)}.
- Lançamentos do dia: POST /v3/finance/finance/getShopBillDetail, header
  `Authorization: Bearer <accessToken>`, corpo {acceptor_code: app_shop_id,
  page_no, page_size ≤ 200, start_date, end_date (YYYYMMDD)}. Até 31 dias por
  consulta, até 3 meses para trás. Só pedidos confirmados pela loja.
- Cada pedido pode ter vários lançamentos (`orderType` 1 venda, 2 estorno,
  3 estorno parcial, 4 estorno pós-venda, 8 perda, 9 troca; 5 = despesa sem
  pedido, ex. anúncio). Valores inteiros em centavos; `settlementAmount` é o que
  a loja recebe por aquele lançamento.

Recebido do pedido = soma dos `settlementAmount` dele. Consultamos 7 dias até
ontem e recalculamos tudo: estorno que chega dias depois entra na conta, e
rodar de novo não muda nada. Ajuste de pedido cuja venda (tipo 1) ficou fora da
janela é ignorado — sem a venda, a soma sairia só com o ajuste.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

import requests
from django.core.cache import cache

from apps.stores.services import pedidos_da_99 as p99
from apps.stores.services import repasse_99

logger = logging.getLogger(__name__)

BASE = 'https://openapi.99food.com/v3'
CHAVE_DO_TOKEN = '99food:token_financeiro'
TAMANHO_DA_PAGINA = 200
JANELA_DIAS = 7
TIMEOUT = 20

VENDA = 1
TIPOS_DE_PEDIDO = {1, 2, 3, 4, 8, 9}


def token_financeiro(renovar: bool = False) -> str:
    if not renovar:
        guardado = cache.get(CHAVE_DO_TOKEN)
        if guardado:
            return guardado
    app_id, segredo = p99._credenciais()
    corpo = p99._ler(requests.post(f'{BASE}/auth/authtoken/signIn',
                                   json={'retailer': app_id, 'secret': segredo}, timeout=TIMEOUT))
    dados = corpo.get('data') if isinstance(corpo.get('data'), dict) else corpo
    token = dados.get('accessToken') or ''
    if not token:
        raise p99.ErroDa99(f"Token financeiro da 99 recusado: {corpo.get('errmsg') or corpo.get('errno')}")
    duracao = max(60, int(dados.get('expiresIn') or 3600) - 300)
    cache.set(CHAVE_DO_TOKEN, token, duracao)
    return token


def _pagina(store, inicio: date, fim: date, pagina: int) -> dict:
    corpo_pedido = {
        'acceptor_code': p99.app_shop_id(store), 'page_no': pagina, 'page_size': TAMANHO_DA_PAGINA,
        'start_date': inicio.strftime('%Y%m%d'), 'end_date': fim.strftime('%Y%m%d'),
    }
    for tentativa in (0, 1):
        resposta = requests.post(
            f'{BASE}/finance/finance/getShopBillDetail', json=corpo_pedido, timeout=TIMEOUT,
            headers={'Authorization': f'Bearer {token_financeiro(renovar=bool(tentativa))}'},
        )
        if resposta.status_code in (401, 403) and not tentativa:
            continue
        corpo = p99._ler(resposta)
        if corpo.get('errno') != 0:
            raise p99.ErroDa99(f"99 recusou o extrato: {corpo.get('errmsg') or corpo.get('errno')}")
        dados = corpo.get('data')
        return dados if isinstance(dados, dict) else {}
    raise p99.ErroDa99('99 recusou o token financeiro')


def lancamentos(store, inicio: date, fim: date) -> list[dict]:
    itens, pagina = [], 1
    while True:
        dados = _pagina(store, inicio, fim, pagina)
        itens.extend(dados.get('data') or [])
        if pagina >= int(dados.get('total_page') or 1):
            return itens
        pagina += 1


def _centavos(valor) -> Decimal:
    return (Decimal(int(valor or 0)) / 100).quantize(Decimal('0.01'))


def linhas_dos_lancamentos(itens: list[dict]) -> list[repasse_99.LinhaExtrato]:
    por_pedido: OrderedDict[str, list[dict]] = OrderedDict()
    for item in itens:
        if int(item.get('orderType') or 0) not in TIPOS_DE_PEDIDO or not item.get('orderId'):
            continue
        por_pedido.setdefault(str(item['orderId']), []).append(item)

    linhas = []
    for n, (order_id, lista) in enumerate(por_pedido.items(), start=1):
        venda = next((i for i in lista if int(i.get('orderType') or 0) == VENDA), None)
        if venda is None:
            continue
        linhas.append(repasse_99.LinhaExtrato(
            numero_da_linha=n,
            pedido=order_id,
            data=repasse_99._data(venda.get('businessDateTime')),
            venda=_centavos(venda.get('mealOriginalAmount')),
            recebido=sum((_centavos(i.get('settlementAmount')) for i in lista), Decimal('0.00')),
        ))
    return linhas


def conciliar_pela_api(store, dia: date, gravar: bool = True) -> dict:
    """Concilia os 7 dias que terminam em `dia` (normalmente ontem)."""
    inicio = dia - timedelta(days=JANELA_DIAS - 1)
    linhas = linhas_dos_lancamentos(lancamentos(store, inicio, dia))
    return repasse_99.conciliar(store, linhas, gravar=gravar, fonte='api')
