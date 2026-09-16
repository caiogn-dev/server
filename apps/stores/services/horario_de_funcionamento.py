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


def faixa_do_dia(horario_do_dia) -> str:
    """"08:00 às 17:00", ou '' quando a loja não informou.

    Sem default inventado: anunciar 10h-20h para quem não configurou é uma
    loja fictícia respondendo pelo cliente.
    """
    abre, fecha = _abre(horario_do_dia), _fecha(horario_do_dia)
    return f"{abre} às {fecha}" if abre and fecha else ''


def _abre(horario_do_dia):
    d = horario_do_dia or {}
    return d.get('open') or d.get('start')


def _fecha(horario_do_dia):
    d = horario_do_dia or {}
    return d.get('close') or d.get('end')
