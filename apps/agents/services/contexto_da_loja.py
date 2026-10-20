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

from apps.stores.services.horario_de_funcionamento import dia_esta_aberto, faixa_do_dia, turnos_do_dia

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


def _turnos(do_dia):
    """[(abre, fecha), ...] como `time`; [] se o dia não abre ou está mal cadastrado.

    Dois turnos (08–13 e 15–17) são dois itens: às 13:30 a loja está fechada
    e reabre "hoje às 15:00", não amanhã.
    """
    if not dia_esta_aberto(do_dia):
        return []
    turnos = []
    for a, f in turnos_do_dia(do_dia):
        abre, fecha = _hora(a), _hora(f)
        if abre and fecha:
            turnos.append((abre, fecha))
    return turnos


def _proxima_abertura(horarios, agora):
    """Primeiro (dia, hora) em que a loja abre depois de `agora`, até 7 dias."""
    for adiante in range(0, 8):
        data = agora + timedelta(days=adiante)
        for abre, _ in _turnos(horarios.get(_DIAS[data.weekday()])):
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
    for abre, fecha in _turnos(horarios.get(_DIAS[agora.weekday()])):
        if abre <= agora.time() <= fecha:
            return f"🟢 AGORA: a loja está ABERTA (fecha hoje às {fecha.strftime('%H:%M')})."

    proxima = _proxima_abertura(horarios, agora)
    reabre = f" Reabre {proxima}." if proxima else ''
    return (
        f"🔴 AGORA: a loja está FECHADA.{reabre}\n"
        "REGRA: NÃO recuse o pedido. Mande o link do cardápio "
        f"{link_do_cardapio(loja)} e diga que dá para fazer o pedido AGENDADO "
        "para quando a loja abrir."
    )


def texto_do_prazo(loja) -> str:
    """O tempo de preparo real e a regra de não prometer horário de chegada.

    Enna, 14/10: "vou entrar em reunião às 13:00" às 12:40, e o agente disse
    que dava, com "uns 40 minutos" de preparo — a própria conta não fechava.
    O pedido saiu às 12:58. O preparo vinha só de passagem; agora vem com a
    regra junto.
    """
    from apps.stores.services.prazo_de_entrega import texto as prazo_de_entrega
    faixa = prazo_de_entrega(loja)
    minutos = int(getattr(loja, 'default_prep_minutes', 0) or 0)
    if faixa:
        return (
            f"⏱️ Prazo de entrega da loja: {faixa} depois do pagamento (preparo + trajeto). "
            "É o prazo que você informa; passou do máximo, é atraso. "
            "NUNCA prometa horário de chegada mais cedo que isso."
        )
    regra = (
        "NUNCA prometa horário de chegada. Se o cliente tiver um horário-limite, "
        "diga a estimativa e que não dá para garantir; ele decide."
    )
    if minutos <= 0:
        return f"⏱️ Tempo de preparo: não cadastrado — não estime minutos. {regra}"
    return f"⏱️ Tempo de preparo: cerca de {minutos} min, mais o trajeto da entrega. {regra}"
