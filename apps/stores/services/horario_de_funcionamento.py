"""Leitura do `operating_hours` da loja — fonte única.

A mesma regra estava escrita em três lugares, e duas cópias estavam erradas:

  - `Store.is_open` — certa (corrigida antes, com o comentário do incidente).
  - `whatsapp/intents/handlers/info.py` — anunciava sábado e domingo como
    08:00-17:00 na Cê Saladas (conversa da Elizandra, 16/set).
  - `whatsapp/intents/handlers/interactive.py::_next_open_slots` — oferecia
    agendamento em dia fechado.

As duas erradas testavam `if hours:` — dict não-vazio é verdadeiro — e nunca
liam `is_open`. Dia fechado mantém `open`/`close` gravados de propósito, para
o lojista não perder a configuração quando reabre o dia. Então "tem horário"
nunca quis dizer "abre".
"""


def verdadeiro(valor) -> bool:
    """JSON de painel chega como bool, "false" ou 0 conforme o formulário.

    `bool("false")` é True, então comparar por truthiness erra calado.
    """
    if isinstance(valor, str):
        return valor.strip().lower() not in ('false', '0', 'no', '')
    return bool(valor)


def dia_esta_aberto(horario_do_dia) -> bool:
    """O dia abre? `is_open` é a resposta; `open`/`close` não são.

    Ausência da chave NÃO fecha: cadastro antigo não tem `is_open`, e nesse
    formato ter horário é o que significa abrir.
    """
    if not horario_do_dia:
        return False
    if 'is_open' in horario_do_dia:
        return verdadeiro(horario_do_dia['is_open'])
    return bool(_abre(horario_do_dia) and _fecha(horario_do_dia))


def turnos_do_dia(horario_do_dia) -> list:
    """[(abre, fecha), ...] do dia. `intervals` manda quando existe (dois
    turnos: 08–13 e 15–17); sem ele, o `open`/`close` de sempre vira um turno.
    """
    d = horario_do_dia or {}
    intervalos = d.get('intervals')
    if isinstance(intervalos, list) and intervalos:
        return [(_abre(i), _fecha(i)) for i in intervalos if isinstance(i, dict)]
    abre, fecha = _abre(d), _fecha(d)
    return [(abre, fecha)] if abre and fecha else []


def dentro_do_horario(horario_do_dia, hora) -> bool:
    """`hora` (datetime.time) cai em algum turno do dia?

    Turno ilegível não abre: erro de digitação no painel não pode pôr a loja
    para vender sem ninguém para entregar.
    """
    from datetime import datetime as _dt

    d = horario_do_dia or {}
    turnos = turnos_do_dia(d)
    if not turnos:
        # Cadastro antigo com `is_open` e sem horário: dia inteiro.
        turnos = [(d.get('open') or '00:00', d.get('close') or '23:59')]
    for abre, fecha in turnos:
        try:
            if _dt.strptime(abre or '00:00', '%H:%M').time() <= hora <= _dt.strptime(fecha or '23:59', '%H:%M').time():
                return True
        except (ValueError, TypeError):
            continue
    return False


def faixa_do_dia(horario_do_dia) -> str:
    """"08:00 às 17:00" (ou "08:00 às 13:00 e 15:00 às 17:00"); '' sem horário.

    Sem default inventado: anunciar 10h-20h para quem não configurou é uma
    loja fictícia respondendo pelo cliente.
    """
    return ' e '.join(f"{a} às {f}" for a, f in turnos_do_dia(horario_do_dia) if a and f)


def pausa_ativa(metadata, agora):
    """A pausa programada que vale em `agora`, ou None.

    `metadata.pausas = [{inicio, fim, motivo}]`, ISO com fuso. Pausa ilegível
    é ignorada — se fechasse, um campo vazio trancaria a loja para sempre.
    """
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone as _tz

    for p in (metadata or {}).get('pausas') or []:
        if not isinstance(p, dict):
            continue
        try:
            inicio, fim = parse_datetime(p.get('inicio') or ''), parse_datetime(p.get('fim') or '')
        except (ValueError, TypeError):
            continue
        if not inicio or not fim:
            continue
        if _tz.is_naive(inicio):
            inicio = _tz.make_aware(inicio)
        if _tz.is_naive(fim):
            fim = _tz.make_aware(fim)
        if inicio <= agora < fim:
            return p
    return None


def _abre(horario_do_dia):
    d = horario_do_dia or {}
    return d.get('open') or d.get('start')


def _fecha(horario_do_dia):
    d = horario_do_dia or {}
    return d.get('close') or d.get('end')
