"""Reserva de 'só uma vez' das mensagens automáticas.

Cada tarefa de `apps/whatsapp/tasks/automation_tasks.py` reimplementava
`cache.add` + `cache.delete` no erro. A regra é uma só: reserva antes de
enviar; se nada saiu, libera para a nova tentativa passar; se saiu, mantém —
senão o cliente recebe duas.
"""
from django.core.cache import cache


def reservar(chave: str, segundos: int) -> bool:
    """True = pode enviar (ninguém reservou esta chave dentro do prazo)."""
    return bool(cache.add(chave, 1, timeout=segundos))


def liberar(chave: str) -> None:
    """Desfaz a reserva — só quando a mensagem NÃO saiu."""
    cache.delete(chave)
