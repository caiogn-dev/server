"""O que o agente sabe sobre a loja estar aberta — e o que ele faz quando não está.

Dois defeitos, um só lugar (`_build_dynamic_context`):

1. O agente recebia o horário da semana, mas nunca "AGORA a loja está
   fechada". Modelo de linguagem não sabe que horas são: ele adivinha.
2. A lista ignorava o dia desligado. A Cê Saladas tem sábado e domingo com
   `is_open: false` e 08:00–17:00 gravados embaixo; o agente lia
   "Sábado: 08:00 às 17:00" — a mesma família do bug de 16/09.

REGRA DO DONO (18/09): loja fechada NÃO recusa pedido. O bot manda o link do
cardápio e diz que dá para pedir com agendamento.
"""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from apps.agents.services.contexto_da_loja import (
    link_do_cardapio,
    texto_de_agora,
    texto_do_horario,
)

BRT = ZoneInfo('America/Sao_Paulo')
DIA_UTIL = {'open': '08:00', 'close': '17:00', 'is_open': True}
DESLIGADO = {'open': '08:00', 'close': '17:00', 'is_open': False}
HORARIOS = {
    'monday': DIA_UTIL, 'tuesday': DIA_UTIL, 'wednesday': DIA_UTIL,
    'thursday': DIA_UTIL, 'friday': DIA_UTIL,
    'saturday': DESLIGADO, 'sunday': DESLIGADO,
}


def _loja(**kw):
    base = dict(slug='ce-saladas', website_url='', custom_domain='', operating_hours=HORARIOS)
    base.update(kw)
    return SimpleNamespace(**base)


# 18/09/2026 é sexta-feira.
SEXTA_10H = datetime(2026, 9, 18, 10, 0, tzinfo=BRT)
SEXTA_20H = datetime(2026, 9, 18, 20, 0, tzinfo=BRT)
SABADO_11H = datetime(2026, 9, 19, 11, 0, tzinfo=BRT)


class TestLinkDoCardapio:
    def test_usa_o_site_da_loja_quando_existe(self):
        assert link_do_cardapio(_loja(website_url='https://cesaladas.com.br/')) == 'https://cesaladas.com.br'

    def test_dominio_proprio_sem_site(self):
        assert link_do_cardapio(_loja(custom_domain='pastita.com.br')) == 'https://pastita.com.br'

    def test_cai_no_cardapidex_sem_nada(self):
        assert link_do_cardapio(_loja()) == 'https://cardapidex.com.br/ce-saladas'


class TestHorarioDaSemana:
    def test_dia_desligado_aparece_fechado_mesmo_com_horario_gravado(self):
        texto = texto_do_horario(_loja())
        assert 'Sábado: FECHADO' in texto
        assert 'Domingo: FECHADO' in texto
        assert 'Sábado: 08:00' not in texto

    def test_dia_aberto_mostra_a_faixa(self):
        assert 'Sexta: 08:00 às 17:00' in texto_do_horario(_loja())


class TestAgora:
    def test_aberta_diz_que_esta_aberta(self):
        texto = texto_de_agora(_loja(), SEXTA_10H)
        assert 'ABERTA' in texto
        assert 'FECHADA' not in texto

    def test_fechada_manda_o_link_e_oferece_agendamento(self):
        texto = texto_de_agora(_loja(website_url='https://cesaladas.com.br'), SEXTA_20H)
        assert 'FECHADA' in texto
        assert 'https://cesaladas.com.br' in texto
        assert 'agend' in texto.lower()

    def test_fechada_nao_manda_recusar(self):
        texto = texto_de_agora(_loja(), SEXTA_20H).lower()
        assert 'não recuse' in texto or 'nao recuse' in texto

    def test_proxima_abertura_pula_o_fim_de_semana_desligado(self):
        """Sábado desligado: a próxima abertura é segunda, não sábado 08:00."""
        texto = texto_de_agora(_loja(), SABADO_11H)
        assert 'segunda' in texto.lower()
        assert '08:00' in texto

    def test_sem_horario_cadastrado_nao_inventa(self):
        texto = texto_de_agora(_loja(operating_hours={}), SEXTA_20H)
        assert texto == ''
