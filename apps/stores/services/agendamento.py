"""Faixas de agendamento — saem do horário da loja, não de uma lista fixa.

Até 21/10 a vitrine tinha 10–12, 12–14, 14–16, 16–18 e 18–20 escritos no
código, para toda loja, e pulava o domingo à mão. A Cê Saladas fecha às 17h e
não abre no sábado; oferecia "sábado, 18:00–20:00". Quem decide agora é o
servidor: os turnos de cada dia (`horario_de_funcionamento`), a pausa
programada e o que o dono configurou em `metadata.agendamento`:

    {'intervalo': 60,     # tamanho da faixa em minutos (30, 60, 90 ou 120)
     'antecedencia': 60,  # hoje, a faixa só começa depois de agora + isto
     'dias_de_antecedencia': 0}  # encomenda: 1º dia aceito = hoje + N, e agendar é obrigatório

A vitrine recebe a agenda pronta no `/availability/`; o checkout recusa faixa
fora do horário; o bot oferece os mesmos horários.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.stores.services.horario_de_funcionamento import dia_esta_aberto, turnos_do_dia

INTERVALOS = (30, 60, 90, 120)
PADRAO = {'intervalo': 60, 'antecedencia': 60, 'dias': 7, 'dias_de_antecedencia': 0}
MAX_DIAS_DE_ANTECEDENCIA = 30
# Quantos dias com horário a vitrine oferece. Banqueteria encomenda festa com
# semanas de antecedência (Ivoneth, 23/11); 7 continua o padrão do delivery.
MAX_HORIZONTE = 90
DIAS_DA_SEMANA = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def config_do_agendamento(store) -> dict:
    """O que o dono escolheu; valor fora do permitido volta ao padrão."""
    bruto = (getattr(store, 'metadata', None) or {}).get('agendamento') or {}
    cfg = dict(PADRAO)
    if bruto.get('intervalo') in INTERVALOS:
        cfg['intervalo'] = bruto['intervalo']
    antecedencia = bruto.get('antecedencia')
    if isinstance(antecedencia, int) and not isinstance(antecedencia, bool) and 0 <= antecedencia <= 24 * 60:
        cfg['antecedencia'] = antecedencia
    horizonte = bruto.get('dias')
    if isinstance(horizonte, int) and not isinstance(horizonte, bool) and 1 <= horizonte <= MAX_HORIZONTE:
        cfg['dias'] = horizonte
    dias = bruto.get('dias_de_antecedencia')
    if isinstance(dias, int) and not isinstance(dias, bool) and 0 <= dias <= MAX_DIAS_DE_ANTECEDENCIA:
        cfg['dias_de_antecedencia'] = dias
    return cfg


def primeiro_dia_aceito(store, agora: datetime) -> date:
    return timezone.localtime(agora).date() + timedelta(days=config_do_agendamento(store)['dias_de_antecedencia'])


def _frase_da_antecedencia(store, agora: datetime) -> str:
    n = config_do_agendamento(store)['dias_de_antecedencia']
    dia = primeiro_dia_aceito(store, agora)
    return (f'Pedidos com no mínimo {n} dia{"s" if n > 1 else ""} de antecedência. '
            f'Escolha uma data a partir de {dia.strftime("%d/%m")}.')


def _minutos(hhmm) -> int | None:
    try:
        h, m = str(hhmm).strip().split(':')
        h, m = int(h), int(m)
    except (ValueError, TypeError, AttributeError):
        return None
    return h * 60 + m if 0 <= h <= 24 and 0 <= m < 60 else None


def _hhmm(minutos: int) -> str:
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def _turnos_em_minutos(store, dia: date) -> list[tuple[int, int]]:
    horario = (getattr(store, 'operating_hours', None) or {}).get(DIAS_DA_SEMANA[dia.weekday()])
    if not dia_esta_aberto(horario):
        return []
    turnos = []
    for abre, fecha in turnos_do_dia(horario):
        a, f = _minutos(abre), _minutos(fecha)
        if a is not None and f is not None and a < f:
            turnos.append((a, f))
    return turnos


def _pausas_do_dia(store, dia: date) -> list[tuple[int, int]]:
    """Pausas programadas que tocam `dia`, em minutos do dia local."""
    from django.utils.dateparse import parse_datetime

    trechos = []
    for p in (getattr(store, 'metadata', None) or {}).get('pausas') or []:
        if not isinstance(p, dict):
            continue
        try:
            inicio, fim = parse_datetime(p.get('inicio') or ''), parse_datetime(p.get('fim') or '')
        except (ValueError, TypeError):
            continue
        if not inicio or not fim:
            continue
        inicio = timezone.localtime(inicio if timezone.is_aware(inicio) else timezone.make_aware(inicio))
        fim = timezone.localtime(fim if timezone.is_aware(fim) else timezone.make_aware(fim))
        if fim.date() < dia or inicio.date() > dia:
            continue
        de = 0 if inicio.date() < dia else inicio.hour * 60 + inicio.minute
        ate = 24 * 60 if fim.date() > dia else fim.hour * 60 + fim.minute
        trechos.append((de, ate))
    return trechos


def faixas_do_dia(store, dia: date, agora: datetime) -> list[str]:
    """['08:00-09:00', ...] que a loja atende em `dia`.

    A sobra do turno vira uma faixa menor (08–17 de 2 em 2 h termina em
    16–17), em vez de prometer até 18h numa loja que fecha às 17h.
    """
    cfg = config_do_agendamento(store)
    agora = timezone.localtime(agora)
    if dia < agora.date() or dia < primeiro_dia_aceito(store, agora):
        return []
    corte = agora.hour * 60 + agora.minute + cfg['antecedencia'] if dia == agora.date() else -1
    pausas = _pausas_do_dia(store, dia)
    faixas = []
    for abre, fecha in _turnos_em_minutos(store, dia):
        inicio = abre
        while inicio < fecha:
            fim = min(inicio + cfg['intervalo'], fecha)
            em_pausa = any(inicio < p_ate and fim > p_de for p_de, p_ate in pausas)
            if inicio >= corte and not em_pausa:
                faixas.append(f'{_hhmm(inicio)}-{_hhmm(fim)}')
            inicio = fim
    return faixas


def agenda(store, agora: datetime | None = None) -> list[dict]:
    """[{'data': 'AAAA-MM-DD', 'faixas': [...]}] dos próximos dias com faixa."""
    agora = timezone.localtime(agora or timezone.now())
    cfg = config_do_agendamento(store)
    dias = []
    # Começa a contar no primeiro dia aceito: com 2 dias de antecedência e
    # horizonte 30, são 30 dias com horário a partir de depois de amanhã.
    # Varre até juntar `dias` dias com horário (loja fechada no fim de semana
    # precisa de mais calendário); o teto evita loop numa loja que nunca abre.
    for offset in range(cfg['dias_de_antecedencia'] + cfg['dias'] * 2 + 7):
        dia = agora.date() + timedelta(days=offset)
        faixas = faixas_do_dia(store, dia, agora)
        if faixas:
            dias.append({'data': dia.isoformat(), 'faixas': faixas})
        if len(dias) >= cfg['dias']:
            break
    return dias


def problema_da_faixa(store, dia: date, faixa: str, agora: datetime) -> str | None:
    """Frase para o cliente se a faixa não pode ser atendida; None se pode.

    Não exige que a faixa bata com o intervalo atual: quem abriu o cardápio
    antes de o dono mudar de 1 h para 30 min ainda manda "12:00-14:00", e isso
    está dentro do horário. O que não passa é horário em que ninguém atende.
    """
    if dia < primeiro_dia_aceito(store, agora):
        return _frase_da_antecedencia(store, agora)
    if not (getattr(store, 'operating_hours', None) or {}):
        return None  # loja sem horário cadastrado: não há contra o que conferir
    partes = str(faixa or '').replace(' ', '').split('-')
    inicio, fim = (_minutos(partes[0]), _minutos(partes[1])) if len(partes) == 2 else (None, None)
    if inicio is None or fim is None or inicio >= fim:
        return 'Horário de agendamento inválido. Escolha um horário da lista.'
    turnos = _turnos_em_minutos(store, dia)
    if not any(abre <= inicio and fim <= fecha for abre, fecha in turnos):
        return 'A loja não atende nesse horário. Escolha outro horário para o agendamento.'
    local = timezone.localtime(agora)
    if dia == local.date() and inicio < local.hour * 60 + local.minute:
        return 'Esse horário já passou. Escolha outro horário para o agendamento.'
    return None


def problema_do_agendamento(store, dia: date | None, faixa: str, agora: datetime) -> str | None:
    """Checkout: encomenda sem data é recusada; com data, vale `problema_da_faixa`."""
    if not (dia and faixa):
        if config_do_agendamento(store)['dias_de_antecedencia'] > 0:
            return _frase_da_antecedencia(store, agora)
        return None
    return problema_da_faixa(store, dia, faixa, agora)
