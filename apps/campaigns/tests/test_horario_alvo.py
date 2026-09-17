"""Quando cada pessoa recebe — a tabela do spec, virada em teste.

A regra: a pessoa recebe no horário da campanha, salvo se a janela dela fechar
antes; aí recebe 1h antes de fechar. Nunca entre 21h e 8h, nunca em outro dia.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.campaigns.services.janela import horario_alvo

SP = 'America/Sao_Paulo'


def sp(ano, mes, dia, hora, minuto=0):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=ZoneInfo(SP))


CAMPANHA = sp(2026, 9, 18, 20)  # sexta, 20h


@pytest.mark.parametrize('ultima_msg, esperado', [
    # fecha 12:00 de hoje → 1h antes (o exemplo do dono)
    (sp(2026, 9, 17, 12), sp(2026, 9, 18, 11)),
    # fecha amanhã 09:00, bem depois das 20h → recebe no horário da campanha
    (sp(2026, 9, 18, 9), CAMPANHA),
    # fecha 20:30 → 19:30
    (sp(2026, 9, 17, 20, 30), sp(2026, 9, 18, 19, 30)),
])
def test_alvo_da_tabela(ultima_msg, esperado):
    assert horario_alvo(ultima_msg + timedelta(hours=24), CAMPANHA, SP) == esperado


def test_quem_nunca_falou_fica_de_fora():
    assert horario_alvo(None, CAMPANHA, SP) is None


def test_janela_ja_fechada_fica_de_fora():
    fecha_em = sp(2026, 9, 15, 20)
    assert horario_alvo(fecha_em, CAMPANHA, SP) is None


def test_alvo_de_madrugada_recua_para_as_21h_da_vespera_e_cai_por_ser_outro_dia():
    """Quem falou ontem às 06:00 teria alvo 05:00 — silêncio.

    Recua para as 21:00 mais recentes ANTES do alvo (ontem), e a regra do
    mesmo dia (D5) derruba: antecipar para ontem não existe.
    """
    fecha_em = sp(2026, 9, 18, 6)
    assert horario_alvo(fecha_em, CAMPANHA, SP) is None


def test_campanha_em_outro_dia_nao_antecipa_ninguem():
    """D5: sem isso, agendar para depois de amanhã antecipava a lista inteira."""
    campanha = sp(2026, 9, 20, 20)
    fecha_em = sp(2026, 9, 18, 12)
    assert horario_alvo(fecha_em, campanha, SP) is None


def test_as_21h_em_ponto_ainda_vale():
    fecha_em = sp(2026, 9, 18, 22)
    campanha = sp(2026, 9, 18, 21)
    assert horario_alvo(fecha_em, campanha, SP) == campanha


def test_a_conta_e_no_fuso_da_loja_nao_no_do_servidor():
    """O container roda em UTC. 23:30 UTC é 20:30 em SP — dentro da faixa.

    Se a faixa fosse medida em UTC, esta campanha seria empurrada para as 21h
    UTC (18h em SP) e sairia três horas antes do que o dono escolheu.
    """
    campanha = datetime(2026, 9, 18, 23, 30, tzinfo=ZoneInfo('UTC'))
    fecha_em = campanha + timedelta(hours=5)
    assert horario_alvo(fecha_em, campanha, SP) == campanha
