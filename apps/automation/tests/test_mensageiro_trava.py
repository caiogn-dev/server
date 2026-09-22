"""Trava única de 'só uma vez' das mensagens automáticas.

Cada tarefa de automation_tasks reimplementava `cache.add` + `cache.delete` no
erro, com variações. A regra é uma: reserva antes de enviar; se nada saiu,
libera para a nova tentativa passar; se saiu, mantém.
"""
import pytest
from django.core.cache import cache

from apps.automation.mensageiro import liberar, reservar


@pytest.fixture(autouse=True)
def _cache():
    cache.clear()
    yield
    cache.clear()


def test_primeira_reserva_pode_enviar():
    assert reservar('pix:1:first', 3600) is True


def test_segunda_reserva_nao_pode():
    reservar('pix:1:first', 3600)
    assert reservar('pix:1:first', 3600) is False


def test_liberar_permite_tentar_de_novo():
    reservar('pix:1:first', 3600)
    liberar('pix:1:first')
    assert reservar('pix:1:first', 3600) is True
