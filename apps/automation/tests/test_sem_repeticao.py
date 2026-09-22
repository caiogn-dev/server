"""Saudação e aviso de loja fechada não se repetem em seguida.

19/09, 30 dias de produção: a saudação saiu em dobro 4 vezes e o aviso de
loja fechada 1 vez. Em TODOS os casos o cliente mandou duas mensagens
seguidas ("Olá" + "Bom dia", 1 a 3 s de diferença) e o bot cumprimentou cada
uma. Não era código duplicado: faltava "já cumprimentei agora há pouco".
"""
import pytest
from django.core.cache import cache

from apps.automation.services.sem_repeticao import (
    JANELA_SEGUNDOS,
    tipo_repetivel,
    ja_mandou_agora,
)
from apps.automation.services.unified_service import ResponseSource, UnifiedResponse


def _resposta(**metadata):
    return UnifiedResponse(content='Olá! Bem-vindo(a)', source=ResponseSource.HANDLER, metadata=metadata)


@pytest.fixture(autouse=True)
def _limpa_cache():
    cache.clear()
    yield
    cache.clear()


class TestTipoRepetivel:
    def test_saudacao(self):
        assert tipo_repetivel(_resposta(intent='greeting')) == 'saudacao'

    def test_boas_vindas_do_modelo(self):
        assert tipo_repetivel(_resposta(event_type='welcome')) == 'saudacao'

    def test_fora_do_horario(self):
        assert tipo_repetivel(_resposta(intent='out_of_hours')) == 'fora_do_horario'

    def test_resposta_de_pedido_nao_e_repetivel(self):
        """Só saudação e aviso de fechado: repetir pedido/PIX pode ser necessário."""
        assert tipo_repetivel(_resposta(intent='create_order')) is None

    def test_resposta_vazia(self):
        assert tipo_repetivel(None) is None


class TestJaMandouAgora:
    def test_primeira_vez_manda(self):
        assert ja_mandou_agora('conv-1', 'saudacao') is False

    def test_segunda_vez_em_seguida_nao_manda(self):
        ja_mandou_agora('conv-1', 'saudacao')
        assert ja_mandou_agora('conv-1', 'saudacao') is True

    def test_outra_conversa_nao_e_afetada(self):
        ja_mandou_agora('conv-1', 'saudacao')
        assert ja_mandou_agora('conv-2', 'saudacao') is False

    def test_tipos_sao_independentes(self):
        ja_mandou_agora('conv-1', 'saudacao')
        assert ja_mandou_agora('conv-1', 'fora_do_horario') is False

    def test_janela_e_de_minutos_nao_de_horas(self):
        assert 5 * 60 <= JANELA_SEGUNDOS <= 30 * 60
