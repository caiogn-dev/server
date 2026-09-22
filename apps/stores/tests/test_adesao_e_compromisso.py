"""A adesão é o que trava a venda — e ela se paga com compromisso.

Medido no catálogo em 22/09: entrar no plano "Loja + WhatsApp" custa
R$ 1.200 de adesão + R$ 249 do primeiro mês = **R$ 1.449 na primeira fatura**.
O preço mensal não é o problema (R$ 249 é o número da estratégia, LTV/CAC 5,5×
contra 1,97× nas faixas baixas). O problema é o degrau da entrada.

Decisão do dono em 22/09: implantação grátis para quem fecha 12 meses, diluída
na mensalidade. A adesão continua existindo para quem não quer se comprometer
— ela custa 7,9 h de trabalho e é real.

Dois testes, duas armadilhas diferentes:
  1. a isenção tem que depender do CICLO, e `charges_setup_fee` só olhava o
     plano;
  2. "paga 10, leva 12" estava escrito em DOIS lugares. Preço em duas fontes
     já divergiu antes neste repo (R$ 329 no código, R$ 249 no documento e nas
     mensagens, tudo ao mesmo tempo, em 11/ago).
"""
from decimal import Decimal

import pytest

from apps.stores import billing


def test_quem_fecha_o_ano_nao_paga_adesao():
    assert billing.cobra_adesao('pro', 'annual') is False
    assert billing.cobra_adesao('starter', 'annual') is False
    assert billing.cobra_adesao('premium', 'annual') is False


def test_quem_nao_se_compromete_continua_pagando_adesao():
    """Sem isso a isenção vira desconto para todo mundo e a implantação
    (7,9 h medidas) passa a sair de graça sem contrapartida."""
    assert billing.cobra_adesao('pro', 'monthly') is True
    assert billing.cobra_adesao('starter', 'monthly') is True


def test_plano_gratis_nunca_cobra_adesao_em_ciclo_nenhum():
    assert billing.cobra_adesao('free', 'monthly') is False
    assert billing.cobra_adesao('free', 'annual') is False


def test_ciclo_desconhecido_cobra_a_adesao():
    """Falha FECHADA: na dúvida, cobra. O contrário regala R$ 1.200 por um
    typo no nome do ciclo."""
    assert billing.cobra_adesao('pro', '') is True
    assert billing.cobra_adesao('pro', None) is True
    assert billing.cobra_adesao('pro', 'anual-novo') is True


def test_o_desconto_anual_tem_UMA_fonte():
    """`annual_price` multiplicava por 10 na mão enquanto
    `ANNUAL_MONTHS_CHARGED = 10` vivia noutro módulo. Duas cópias do mesmo
    número: mudar uma e esquecer a outra faz a fatura e a vitrine
    discordarem."""
    from apps.stores.services.pix_billing_service import ANNUAL_MONTHS_CHARGED

    assert billing.MESES_COBRADOS_NO_ANUAL == ANNUAL_MONTHS_CHARGED
    assert billing.annual_price('pro') == Decimal('249.00') * ANNUAL_MONTHS_CHARGED


def test_o_que_o_lojista_economiza_fechando_o_ano():
    """O número que vai para a tela. Mensal sem compromisso durante 12 meses
    custa adesão + 12 mensalidades; o anual custa 10 mensalidades."""
    economia = billing.economia_do_anual('pro')

    assert economia['sem_compromisso'] == Decimal('1200.00') + Decimal('249.00') * 12
    assert economia['anual'] == Decimal('249.00') * 10
    assert economia['economia'] == economia['sem_compromisso'] - economia['anual']
    assert economia['economia'] > 0


def test_catalogo_publico_conta_a_oferta_inteira():
    """A tela não pode ter que recalcular a oferta.

    Enquanto o painel montava o preço sozinho, o repo teve TRÊS fontes de preço
    discordando ao mesmo tempo (11/ago). O backend manda o número pronto.
    """
    catalogo = {p['key']: p for p in billing.public_catalog()}
    pro = catalogo['pro']

    assert pro['annual_price'] == 2490.0
    # Sem isto a tela não tem como dizer "implantação grátis" com honestidade.
    assert pro['adesao_no_anual'] == 0.0
    assert pro['adesao_no_mensal'] == 1200.0
    assert pro['economia_no_anual'] == 1200.0 + 249.0 * 12 - 2490.0

    # O plano grátis não inventa oferta nenhuma.
    assert 'annual_price' not in catalogo['free']
    assert catalogo['free']['adesao_no_mensal'] == 0.0
