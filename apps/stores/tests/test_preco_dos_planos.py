"""O plano com bot custa R$ 249 — o número da estratégia, não o antigo 329.

`estrategia-monetizacao-2026-08-02.md` precifica "o que já existe" em R$ 249/mês
+ R$ 1.200 de implantação, com LTV/CAC de 5,5× contra 1,97× nas faixas baixas.
O bot do WhatsApp é o único motivo real de compra, então é ele que carrega esse
preço — e por isso o número vive no plano `pro`, não num plano novo.

Travado em teste porque preço é a coisa que mais silenciosamente diverge entre
o catálogo, a landing e a mensagem de prospecção: em 11/ago as três diziam
coisas diferentes ao mesmo tempo.
"""
from decimal import Decimal

from apps.stores.billing import PLAN_CATALOG


def test_plano_com_bot_custa_249():
    assert PLAN_CATALOG['pro']['monthly_price'] == Decimal('249.00')


def test_implantacao_e_1200_em_todo_plano_pago():
    for chave in ('starter', 'pro', 'premium'):
        assert PLAN_CATALOG[chave]['setup_fee'] == Decimal('1200.00'), chave


def test_gratis_nao_cobra_nada():
    assert PLAN_CATALOG['free']['monthly_price'] == Decimal('0.00')
    assert PLAN_CATALOG['free']['charges_setup_fee'] is False


def test_escada_de_preco_e_crescente():
    """Plano mais caro tem que custar mais — parece óbvio e já foi violado."""
    ordem = ['free', 'starter', 'pro', 'premium']
    precos = [PLAN_CATALOG[k]['monthly_price'] for k in ordem]
    assert precos == sorted(precos), precos


def test_cada_degrau_acrescenta_algo():
    """Degrau que não libera nada novo não é degrau: é o mesmo plano mais caro.

    Era o caso na landing — Rede e Loja+WhatsApp mostravam a MESMA lista, e o
    que justifica os R$ 300 a mais (3 lojas) não aparecia em lugar nenhum.
    """
    ordem = ['free', 'starter', 'pro', 'premium']
    for anterior, atual in zip(ordem, ordem[1:]):
        a = PLAN_CATALOG[anterior]['limits']
        b = PLAN_CATALOG[atual]['limits']
        ganhou = [
            k for k, v in b.items()
            if v is True and a.get(k) is not True
        ]
        # limite numérico que virou ilimitado também conta como ganho
        ganhou += [
            k for k in ('max_products', 'max_orders_per_month')
            if a.get(k) is not None and b.get(k) is None
        ]
        # e mais lojas é ganho
        if (b.get('max_stores') or 1) > (a.get('max_stores') or 1):
            ganhou.append('max_stores')
        assert ganhou, f'{atual} não acrescenta nada sobre {anterior}'


def test_nenhum_outro_teste_afirma_preco_diferente():
    """Duas suítes afirmando preços diferentes é o bug da semana, em teste.

    `test_plan_catalog_golive` travava 329 enquanto este arquivo trava 249 — e
    as duas passavam isoladas. Quem rodasse só uma acreditaria nela.

    Este teste lê os literais do OUTRO arquivo e cobra que batam com o catálogo.
    Preço é a coisa que mais silenciosamente diverge neste projeto: em 11/ago o
    billing dizia 329, o documento de estratégia 249 e as mensagens de
    prospecção 249, tudo ao mesmo tempo.
    """
    import re
    from pathlib import Path

    outro = Path(__file__).with_name('test_plan_catalog_golive.py').read_text()
    afirmados = dict(re.findall(r"\('(\w+)', '([\d.]+)'\)", outro))

    for chave, preco in afirmados.items():
        assert PLAN_CATALOG[chave]['monthly_price'] == Decimal(preco), (
            f'{chave}: catálogo diz {PLAN_CATALOG[chave]["monthly_price"]}, '
            f'test_plan_catalog_golive diz {preco}'
        )
