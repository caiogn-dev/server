"""Reserva de 'só uma vez' das mensagens automáticas.

Cada tarefa de `apps/whatsapp/tasks/automation_tasks.py` reimplementava
`cache.add` + `cache.delete` no erro. A regra é uma só: reserva antes de
enviar; se nada saiu, libera para a nova tentativa passar; se saiu, mantém —
senão o cliente recebe duas.
"""
from contextlib import contextmanager
from django.core.cache import cache


def reservar(chave: str, segundos: int) -> bool:
    """True = pode enviar (ninguém reservou esta chave dentro do prazo)."""
    return bool(cache.add(chave, 1, timeout=segundos))


def liberar(chave: str) -> None:
    """Desfaz a reserva — só quando a mensagem NÃO saiu."""
    cache.delete(chave)


class _Envio:
    """Anota se alguma mensagem chegou a sair nesta tentativa."""

    def __init__(self):
        self.saiu_algo = False

    def saiu(self):
        self.saiu_algo = True


@contextmanager
def envio_unico(chave: str, segundos: int):
    """A moldura de toda tarefa de envio automático.

    Devolve `None` quando a chave já estava reservada — a tarefa é duplicada e
    deve sair sem fazer nada. Em erro, libera a reserva SÓ se nada saiu: se a
    mensagem já foi, repetir manda duas para o cliente.
    """
    if not reservar(chave, segundos):
        yield None
        return

    envio = _Envio()
    try:
        yield envio
    except Exception:
        if not envio.saiu_algo:
            liberar(chave)
        raise
