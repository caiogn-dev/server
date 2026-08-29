"""
Dia marcado como fechado no painel tem de fechar a loja.

O dono marcou sábado como fechado e o site continuou vendendo. O motivo:
`Store.is_open()` lia só `open` e `close` do dia e comparava com a hora atual
— o `is_open: false` que o painel grava dentro do dia era simplesmente
ignorado. Sábado tinha `{"open": "08:00", "close": "12:00", "is_open": false}`,
então das 8 às 12 a loja abria contra a vontade de quem a administra.

Segundo problema, mais silencioso: qualquer horário malformado caía num
`except: return True`. Um erro de digitação no painel ABRIA a loja — o
contrário do que um fallback de segurança deveria fazer.
"""
from datetime import datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.models import User
from apps.stores.models import Store


pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(
        username='dono-horario', email='dono-horario@example.com', password='x'
    )
    return Store.objects.create(name='Horário', slug='horario', owner=dono)


def _em(loja, quando: str, horarios: dict):
    """Avalia is_open() como se agora fosse `quando` (ISO)."""
    loja.operating_hours = horarios
    momento = timezone.make_aware(datetime.fromisoformat(quando))
    with patch.object(timezone, 'localtime', return_value=momento):
        return loja.is_open()


# 2026-08-29 é um SÁBADO; 2026-08-28, uma sexta.
SABADO_MANHA = '2026-08-29T10:00:00'
SEXTA_MANHA = '2026-08-28T10:00:00'

FECHADO_SABADO = {
    'friday':   {'open': '08:00', 'close': '17:00', 'is_open': True},
    'saturday': {'open': '08:00', 'close': '12:00', 'is_open': False},
}


class TestDiaDesligado:
    def test_sabado_marcado_como_fechado_nao_abre_dentro_do_horario(self, loja):
        # O caso real: 10h de sábado, dentro do 08:00–12:00 gravado.
        assert _em(loja, SABADO_MANHA, FECHADO_SABADO) is False

    def test_os_outros_dias_seguem_abrindo(self, loja):
        assert _em(loja, SEXTA_MANHA, FECHADO_SABADO) is True

    def test_dia_sem_o_campo_continua_valendo_pelo_horario(self, loja):
        # Cadastro antigo não tem `is_open`. Ausência não pode fechar a loja.
        horarios = {'saturday': {'open': '08:00', 'close': '12:00'}}
        assert _em(loja, SABADO_MANHA, horarios) is True

    @pytest.mark.parametrize('valor', [False, 'false', 0])
    def test_entende_as_formas_de_desligado_que_o_painel_grava(self, loja, valor):
        horarios = {'saturday': {'open': '08:00', 'close': '12:00', 'is_open': valor}}
        assert _em(loja, SABADO_MANHA, horarios) is False

    def test_dia_ausente_no_cadastro_fecha(self, loja):
        assert _em(loja, SABADO_MANHA, {'friday': {'open': '08:00', 'close': '17:00'}}) is False


class TestHorario:
    def test_fora_da_janela_fecha(self, loja):
        horarios = {'saturday': {'open': '08:00', 'close': '12:00', 'is_open': True}}
        assert _em(loja, '2026-08-29T14:00:00', horarios) is False

    def test_dentro_da_janela_abre(self, loja):
        horarios = {'saturday': {'open': '08:00', 'close': '12:00', 'is_open': True}}
        assert _em(loja, SABADO_MANHA, horarios) is True

    def test_sem_horario_nenhum_a_loja_abre(self, loja):
        # Loja que nunca configurou horário não pode ficar presa fechada.
        assert _em(loja, SABADO_MANHA, {}) is True


class TestHorarioQuebrado:
    def test_horario_malformado_FECHA_em_vez_de_abrir(self, loja):
        # Era `return True`: um erro de digitação no painel abria a loja.
        # Diante da dúvida, não vender é recuperável; vender sem poder entregar
        # custa o cliente.
        horarios = {'saturday': {'open': 'oito', 'close': 'meio-dia', 'is_open': True}}
        assert _em(loja, SABADO_MANHA, horarios) is False

    def test_dia_desligado_vence_ate_horario_quebrado(self, loja):
        horarios = {'saturday': {'open': 'xx', 'close': 'yy', 'is_open': False}}
        assert _em(loja, SABADO_MANHA, horarios) is False
