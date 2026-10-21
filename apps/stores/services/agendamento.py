"""Faixas de agendamento — saem do horário da loja, não de uma lista fixa.

Até 21/10 a vitrine tinha 10–12, 12–14, 14–16, 16–18 e 18–20 escritos no
código, para toda loja, e pulava o domingo à mão. A Cê Saladas fecha às 17h e
não abre no sábado; oferecia "sábado, 18:00–20:00". Quem decide agora é o
servidor: os turnos de cada dia (`horario_de_funcionamento`), a pausa
programada e o que o dono configurou em `metadata.agendamento`:

    {'intervalo': 60,     # tamanho da faixa em minutos (30, 60, 90 ou 120)
     'antecedencia': 60}  # hoje, a faixa só começa depois de agora + isto

A vitrine recebe a agenda pronta no `/availability/`; o checkout recusa faixa
fora do horário; o bot oferece os mesmos horários.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.stores.services.horario_de_funcionamento import dia_esta_aberto, turnos_do_dia

INTERVALOS = (30, 60, 90, 120)
PADRAO = {'intervalo': 60, 'antecedencia': 60, 'dias': 7}
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
    return cfg


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
    if dia < agora.date():
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
    for offset in range(cfg['dias'] + 1):
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
