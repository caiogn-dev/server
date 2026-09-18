"""Aberta ou fechada AGORA — e o que o agente faz com isso.

O agente recebia só o horário da semana e adivinhava se a loja estava aberta
(modelo de linguagem não sabe que horas são). E a lista ignorava o dia
desligado: a Cê Saladas tem sábado e domingo `is_open: false` com 08:00–17:00
gravados, e o agente lia "Sábado: 08:00 às 17:00".

REGRA DO DONO (18/09/2026): loja fechada NÃO recusa pedido. O agente manda o
link do cardápio e diz que dá para pedir com agendamento.

Funções puras: recebem a loja e o instante, e a regra de "dia aberto" é a
fonte única de `horario_de_funcionamento` — a mesma do `Store.is_open`.
"""
from datetime import datetime, timedelta

from apps.stores.services.horario_de_funcionamento import dia_esta_aberto, faixa_do_dia

_DIAS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
_DIA_PT = {
    'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
    'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado', 'sunday': 'Domingo',
}


def link_do_cardapio(loja) -> str:
    """Onde o cliente faz o pedido: site da loja > domínio próprio > Cardapidex."""
    site = (getattr(loja, 'website_url', '') or '').strip().rstrip('/')
    if site:
        return site
    dominio = (getattr(loja, 'custom_domain', '') or '').strip().strip('/')
    if dominio:
        return f'https://{dominio}'
    return f"https://cardapidex.com.br/{getattr(loja, 'slug', '')}"


def texto_do_horario(loja) -> str:
    horarios = getattr(loja, 'operating_hours', None) or {}
    if not horarios:
        return ''
    linhas = ['⏰ HORÁRIO DE FUNCIONAMENTO:']
    for dia in _DIAS:
        do_dia = horarios.get(dia)
        faixa = faixa_do_dia(do_dia) if dia_esta_aberto(do_dia) else ''
        linhas.append(f"• {_DIA_PT[dia]}: {faixa or 'FECHADO'}")
    return '\n'.join(linhas)


def _hora(texto):
    try:
        return datetime.strptime(texto, '%H:%M').time()
    except (TypeError, ValueError):
        return None


def _faixa(do_dia):
    """(abre, fecha) como `time`, ou None se o dia não abre ou está mal cadastrado."""
    if not dia_esta_aberto(do_dia):
        return None
    abre = _hora(do_dia.get('open') or do_dia.get('start'))
    fecha = _hora(do_dia.get('close') or do_dia.get('end'))
    if not abre or not fecha:
        return None
    return abre, fecha


def _proxima_abertura(horarios, agora):
    """Primeiro (dia, hora) em que a loja abre depois de `agora`, até 7 dias."""
    for adiante in range(0, 8):
        data = agora + timedelta(days=adiante)
        faixa = _faixa(horarios.get(_DIAS[data.weekday()]))
        if not faixa:
            continue
        abre, _ = faixa
        if adiante == 0 and agora.time() >= abre:
            continue
        if adiante == 0:
            quando = 'hoje'
        elif adiante == 1:
            quando = 'amanhã'
        else:
            quando = _DIA_PT[_DIAS[data.weekday()]].lower()
        return f"{quando} às {abre.strftime('%H:%M')}"
    return ''


def texto_de_agora(loja, agora) -> str:
    """A linha que diz ao agente se a loja está aberta AGORA e o que fazer."""
    horarios = getattr(loja, 'operating_hours', None) or {}
    if not horarios:
        return ''  # sem horário cadastrado não se inventa aberta nem fechada
    faixa = _faixa(horarios.get(_DIAS[agora.weekday()]))
    if faixa and faixa[0] <= agora.time() <= faixa[1]:
        return f"🟢 AGORA: a loja está ABERTA (fecha hoje às {faixa[1].strftime('%H:%M')})."

    proxima = _proxima_abertura(horarios, agora)
    reabre = f" Reabre {proxima}." if proxima else ''
    return (
        f"🔴 AGORA: a loja está FECHADA.{reabre}\n"
        "REGRA: NÃO recuse o pedido. Mande o link do cardápio "
        f"{link_do_cardapio(loja)} e diga que dá para fazer o pedido AGENDADO "
        "para quando a loja abrir."
    )
