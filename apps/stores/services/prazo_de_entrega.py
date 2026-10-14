"""Prazo de entrega que o cliente vê — "30–45 min" e "chega entre 13:14 e 13:29".

A vitrine mostrava "~3 min" (só o trajeto da rota) e a loja recebia reclamação
de demora em pedido dentro do prazo (14/10). O prazo agora é da LOJA, em duas
colunas do Store, e todo lugar que fala com o cliente lê daqui.
"""
from datetime import timedelta

from django.utils import timezone


def faixa(loja):
    """(mínimo, máximo) em minutos, ou None quando a loja não promete prazo."""
    maximo = int(getattr(loja, 'prazo_entrega_max', 0) or 0)
    if maximo <= 0:
        return None
    minimo = int(getattr(loja, 'prazo_entrega_min', 0) or 0)
    return (minimo if 0 < minimo <= maximo else 0, maximo)


def texto(loja) -> str:
    f = faixa(loja)
    if not f:
        return ''
    minimo, maximo = f
    return f'{minimo}–{maximo} min' if minimo else f'até {maximo} min'


def janela(loja, inicio) -> str:
    """"13:14 e 13:29": a faixa em horário de relógio, a partir de `inicio`."""
    f = faixa(loja)
    if not f:
        return ''
    local = timezone.localtime(inicio) if timezone.is_aware(inicio) else inicio
    minimo, maximo = f
    return f"{(local + timedelta(minutes=minimo or maximo)).strftime('%H:%M')} e {(local + timedelta(minutes=maximo)).strftime('%H:%M')}"


def para_vitrine(loja):
    f = faixa(loja)
    if not f:
        return None
    return {'min': f[0], 'max': f[1], 'texto': texto(loja)}
