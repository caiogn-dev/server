"""A moldura repetida de toda tarefa de envio automático.

As cinco tarefas escreviam o mesmo esqueleto: reservar a chave, `enviado =
False`, try/except, liberar a trava só se nada saiu, `self.retry`. Cinco
cópias da mesma regra sutil — e a sutileza importa: liberar depois de a
mensagem ter saído faz o cliente receber duas vezes.
"""
import pytest
from django.core.cache import cache

from apps.automation.mensageiro import envio_unico, reservar


@pytest.fixture(autouse=True)
def _limpo():
    cache.clear()
    yield
    cache.clear()


def test_primeira_vez_entra():
    entrou = False
    with envio_unico('k1', 60) as envio:
        entrou = envio is not None
    assert entrou


def test_segunda_vez_nao_entra():
    with envio_unico('k2', 60):
        pass

    with envio_unico('k2', 60) as envio:
        assert envio is None


def test_falha_sem_envio_libera_a_trava():
    with pytest.raises(RuntimeError):
        with envio_unico('k3', 60):
            raise RuntimeError('meta fora do ar')

    # Liberada: a próxima tentativa precisa passar.
    assert reservar('k3', 60) is True


def test_falha_depois_do_envio_mantem_a_trava():
    """Se a mensagem já saiu, repetir manda duas para o cliente."""
    with pytest.raises(RuntimeError):
        with envio_unico('k4', 60) as envio:
            envio.saiu()
            raise RuntimeError('erro depois do envio')

    assert reservar('k4', 60) is False


def test_sucesso_mantem_a_trava():
    with envio_unico('k5', 60) as envio:
        envio.saiu()

    assert reservar('k5', 60) is False
