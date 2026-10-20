"""
Dois turnos no dia e pausa programada com motivo.

A Agrião entrega das 08:00 às 13:00 e das 15:00 às 17:00 (está assim no
Prefiro). Com uma janela só por dia, ou a loja abria no almoço, quando ninguém
sai para entregar, ou fechava a tarde inteira.

Pausa programada é o "fechado sábado para inventário" / "volta às 14h, faltou
gás": um intervalo com início e fim que fecha a loja sem mexer na grade da
semana — e que se desfaz sozinho, sem o dono lembrar de reabrir.

Formato (retrocompatível — dia sem `intervals` segue o `open`/`close`):
    operating_hours.friday = {is_open: true, open: '08:00', close: '17:00',
                              intervals: [{open: '08:00', close: '13:00'},
                                          {open: '15:00', close: '17:00'}]}
    metadata.pausas = [{inicio: ISO, fim: ISO, motivo: str}]
"""
from datetime import datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.models import User
from apps.stores.models import Store
from apps.stores.services.horario_de_funcionamento import faixa_do_dia, pausa_ativa

pytestmark = pytest.mark.django_db

SEXTA = {
    'friday': {
        'is_open': True, 'open': '08:00', 'close': '17:00',
        'intervals': [{'open': '08:00', 'close': '13:00'}, {'open': '15:00', 'close': '17:00'}],
    },
}


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-turno', email='dono-turno@example.com', password='x')
    return Store.objects.create(name='Turnos', slug='turnos', owner=dono, operating_hours=SEXTA)


def _quando(iso):
    return timezone.make_aware(datetime.fromisoformat(iso))


def _aberta(loja, iso):
    with patch.object(timezone, 'localtime', return_value=_quando(iso)), \
         patch.object(timezone, 'now', return_value=_quando(iso)):
        return loja.is_open()


# 2026-10-23 é sexta.
class TestDoisTurnos:
    @pytest.mark.parametrize('hora,aberta', [
        ('09:00', True), ('13:30', False), ('15:00', True), ('16:59', True), ('17:30', False),
    ])
    def test_abre_so_dentro_dos_turnos(self, loja, hora, aberta):
        assert _aberta(loja, f'2026-10-23T{hora}:00') is aberta

    def test_faixa_do_dia_lista_os_dois_turnos(self):
        assert faixa_do_dia(SEXTA['friday']) == '08:00 às 13:00 e 15:00 às 17:00'

    def test_dia_sem_intervals_segue_open_close(self, loja):
        loja.operating_hours = {'friday': {'is_open': True, 'open': '08:00', 'close': '17:00'}}
        assert _aberta(loja, '2026-10-23T14:00:00') is True

    def test_turno_ilegivel_fecha(self, loja):
        loja.operating_hours = {'friday': {'is_open': True, 'intervals': [{'open': '8h', 'close': '13:00'}]}}
        assert _aberta(loja, '2026-10-23T10:00:00') is False


class TestPausaProgramada:
    PAUSA = {'inicio': '2026-10-23T10:00:00-03:00', 'fim': '2026-10-23T12:00:00-03:00', 'motivo': 'Faltou gás'}

    def test_pausa_fecha_dentro_do_turno_e_reabre_sozinha(self, loja):
        loja.metadata = {'pausas': [self.PAUSA]}
        assert _aberta(loja, '2026-10-23T09:59:00') is True
        assert _aberta(loja, '2026-10-23T11:00:00') is False
        assert _aberta(loja, '2026-10-23T12:01:00') is True

    def test_pausa_vale_ate_para_loja_sem_grade(self, loja):
        loja.operating_hours = {}
        loja.metadata = {'pausas': [self.PAUSA]}
        assert _aberta(loja, '2026-10-23T11:00:00') is False

    def test_pausa_ativa_devolve_motivo_e_fim(self, loja):
        loja.metadata = {'pausas': [self.PAUSA]}
        p = pausa_ativa(loja.metadata, _quando('2026-10-23T11:00:00'))
        assert p['motivo'] == 'Faltou gás'
        assert p['fim'] == self.PAUSA['fim']
        assert pausa_ativa(loja.metadata, _quando('2026-10-23T13:00:00')) is None

    def test_pausa_malformada_e_ignorada(self, loja):
        # Pausa ilegível não pode fechar a loja para sempre.
        loja.metadata = {'pausas': [{'inicio': 'ontem', 'fim': None}]}
        assert _aberta(loja, '2026-10-23T11:00:00') is True

    def test_availability_publica_conta_a_pausa(self, loja):
        from rest_framework.test import APIClient
        loja.status = 'active'
        loja.metadata = {'pausas': [self.PAUSA]}
        loja.save()
        with patch.object(timezone, 'localtime', return_value=_quando('2026-10-23T11:00:00')), \
             patch.object(timezone, 'now', return_value=_quando('2026-10-23T11:00:00')):
            r = APIClient().get(f'/api/v1/public/{loja.slug}/availability/')
        assert r.status_code == 200, r.content
        corpo = r.json()
        assert corpo['is_open'] is False
        assert corpo['pausa'] == {'fim': self.PAUSA['fim'], 'motivo': 'Faltou gás'}


class TestAgenteVeOsTurnos:
    def test_no_intervalo_reabre_hoje_a_tarde(self, loja):
        from apps.agents.services.contexto_da_loja import texto_de_agora
        texto = texto_de_agora(loja, _quando('2026-10-23T13:30:00'))
        assert 'FECHADA' in texto
        assert 'Reabre hoje às 15:00' in texto

    def test_no_segundo_turno_esta_aberta(self, loja):
        from apps.agents.services.contexto_da_loja import texto_de_agora
        assert 'fecha hoje às 17:00' in texto_de_agora(loja, _quando('2026-10-23T15:30:00'))
