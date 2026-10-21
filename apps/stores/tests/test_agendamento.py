"""
Faixas de agendamento saem do horário da loja (21/10).

A vitrine tinha uma lista fixa — 10–12 até 18–20, domingo pulado à mão — para
toda loja. A Cê Saladas fecha às 17h e não abre no sábado, e oferecia
"sábado, 18:00–20:00". Agora o servidor monta as faixas pelos turnos de cada
dia, no intervalo que o dono escolhe, e o checkout recusa faixa fora do horário.
"""
from datetime import date, datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.services.agendamento import agenda, config_do_agendamento, faixas_do_dia, problema_da_faixa
from apps.stores.tests.factories import make_store

pytestmark = pytest.mark.django_db

SEMANA = {d: {'open': '08:00', 'close': '17:00', 'is_open': True}
          for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')}
SEMANA.update({'saturday': {'open': '08:00', 'close': '17:00', 'is_open': False},
               'sunday': {'open': '08:00', 'close': '17:00', 'is_open': False}})

# 2026-10-21 é quarta; 24 sábado; 26 segunda.
QUARTA, SABADO, SEGUNDA = date(2026, 10, 21), date(2026, 10, 24), date(2026, 10, 26)


def _agora(iso):
    return timezone.make_aware(datetime.fromisoformat(iso))


@pytest.fixture
def loja():
    s = make_store()
    s.operating_hours = SEMANA
    s.metadata = {}
    s.save(update_fields=['operating_hours', 'metadata'])
    return s


def _config(loja, **cfg):
    loja.metadata = {**(loja.metadata or {}), 'agendamento': cfg}
    loja.save(update_fields=['metadata'])


class TestFaixas:
    def test_de_hora_em_hora_dentro_do_expediente(self, loja):
        faixas = faixas_do_dia(loja, SEGUNDA, _agora('2026-10-21T09:00'))
        assert faixas[0] == '08:00-09:00' and faixas[-1] == '16:00-17:00' and len(faixas) == 9
        assert not any(f.startswith('17') or f.startswith('18') for f in faixas)

    def test_meia_hora(self, loja):
        _config(loja, intervalo=30)
        faixas = faixas_do_dia(loja, SEGUNDA, _agora('2026-10-21T09:00'))
        assert faixas[:2] == ['08:00-08:30', '08:30-09:00'] and faixas[-1] == '16:30-17:00'

    def test_sobra_do_turno_vira_faixa_menor(self, loja):
        _config(loja, intervalo=120)
        assert faixas_do_dia(loja, SEGUNDA, _agora('2026-10-21T09:00'))[-1] == '16:00-17:00'

    def test_dia_fechado_nao_tem_faixa(self, loja):
        assert faixas_do_dia(loja, SABADO, _agora('2026-10-21T09:00')) == []

    def test_dois_turnos_nao_oferecem_o_intervalo(self, loja):
        loja.operating_hours = {**SEMANA, 'monday': {'open': '08:00', 'close': '17:00', 'is_open': True,
                                                     'intervals': [{'open': '08:00', 'close': '11:00'},
                                                                   {'open': '14:00', 'close': '16:00'}]}}
        loja.save(update_fields=['operating_hours'])
        assert faixas_do_dia(loja, SEGUNDA, _agora('2026-10-21T09:00')) == [
            '08:00-09:00', '09:00-10:00', '10:00-11:00', '14:00-15:00', '15:00-16:00']

    def test_hoje_respeita_a_antecedencia(self, loja):
        faixas = faixas_do_dia(loja, QUARTA, _agora('2026-10-21T10:20'))
        assert faixas[0] == '12:00-13:00'  # 10:20 + 60 min = 11:20 → primeira que começa depois
        _config(loja, antecedencia=30)
        assert faixas_do_dia(loja, QUARTA, _agora('2026-10-21T10:20'))[0] == '11:00-12:00'

    def test_pausa_programada_tira_as_faixas(self, loja):
        loja.metadata = {'pausas': [{'inicio': '2026-10-26T12:00:00-03:00', 'fim': '2026-10-26T14:00:00-03:00'}]}
        loja.save(update_fields=['metadata'])
        faixas = faixas_do_dia(loja, SEGUNDA, _agora('2026-10-21T09:00'))
        assert '12:00-13:00' not in faixas and '13:00-14:00' not in faixas and '14:00-15:00' in faixas

    def test_agenda_pula_dias_sem_faixa(self, loja):
        dias = agenda(loja, _agora('2026-10-21T16:30'))
        assert dias[0]['data'] == '2026-10-22'  # hoje já passou
        assert '2026-10-24' not in [d['data'] for d in dias]
        assert len(dias) <= 7

    def test_config_invalida_cai_no_padrao(self, loja):
        _config(loja, intervalo=7, antecedencia=-5)
        assert config_do_agendamento(loja) == {'intervalo': 60, 'antecedencia': 60, 'dias': 7}


class TestValidacao:
    agora = _agora('2026-10-21T09:00')

    @pytest.mark.parametrize('dia,faixa', [
        (SABADO, '10:00-12:00'), (SEGUNDA, '18:00-20:00'), (SEGUNDA, '16:00-18:00'), (SEGUNDA, 'qualquer'),
    ])
    def test_recusa_fora_do_horario(self, loja, dia, faixa):
        assert problema_da_faixa(loja, dia, faixa, self.agora)

    def test_aceita_faixa_antiga_dentro_do_horario(self, loja):
        # Página aberta antes da mudança ainda manda 12–14: está dentro, passa.
        assert problema_da_faixa(loja, SEGUNDA, '12:00-14:00', self.agora) is None

    def test_loja_sem_horario_nao_bloqueia(self, loja):
        loja.operating_hours = {}
        loja.save(update_fields=['operating_hours'])
        assert problema_da_faixa(loja, SEGUNDA, '18:00-20:00', self.agora) is None


def test_availability_leva_a_agenda(loja):
    r = APIClient().get(f'/api/v1/public/{loja.slug}/availability/')
    assert r.status_code == 200
    assert r.data['agendamento']['intervalo'] == 60
    assert all(f.count('-') == 1 for d in r.data['agendamento']['dias'] for f in d['faixas'])
