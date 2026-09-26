"""Vigia de impressão: o sistema descobre que a cozinha parou de imprimir.

Em 23/09/2026 a impressora da Cê Saladas parou às 19:00 (EPSON `NotAvailable`,
10 impressões presas no spooler do Windows) e ficou assim até a tarde do dia
seguinte — 14 comandas falhas — sem que o painel avisasse ninguém. Quem
descobria era o cliente, perguntando pelo pedido.

Duas situações, na ordem em que doem:

- `offline`: o programa de impressão no PC não fala com o servidor há mais de
  ~3 minutos (PC desligado, serviço parado, sem internet).
- `impressora_indisponivel`: o programa está vivo mas a impressora não imprime
  — a última coisa que aconteceu depois do último sucesso foi uma falha DA
  IMPRESSORA (desligada, USB solta, fila presa). Falha de software (template
  desconhecido) não conta: isso é bug, não impressora.

O painel lê a situação pelo serializer do agente (tela de Impressão). Não
manda aviso nenhum: o dono decidiu em 26/09 que não quer aviso de impressora.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone


logger = logging.getLogger(__name__)

# Versão do pastita-print-agent que o painel considera atual. Bumpar junto com
# o `package.json` do agent: é o que acende "atualize o programa de impressão".
VERSAO_ATUAL_DO_AGENT = '0.4.0'

# Heartbeat é a cada 30 s; 3 minutos = seis batidas perdidas, sem falso alarme
# por um soluço de rede.
OFFLINE_APOS = timedelta(minutes=3)

# Trechos que o agent grava em `last_error` quando é a IMPRESSORA que falhou
# (ver pastita-print-agent/scripts/windows-print-raw.ps1).
_SINAIS_DE_IMPRESSORA = ('is not ready', 'stayed in queue', 'NotAvailable', 'Offline')
_RE_NOT_READY = re.compile(r"Printer '(?P<nome>[^']+)' is not ready.*?jobs=(?P<presas>\d+)", re.S)
_RE_PRESA = re.compile(r'stayed in queue')


@dataclass(frozen=True)
class Situacao:
    codigo: str  # 'ok' | 'offline' | 'impressora_indisponivel'
    desde: datetime | None
    detalhe: str

    @property
    def parada(self) -> bool:
        return self.codigo != 'ok'


OK = Situacao('ok', None, '')


def _minutos(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _detalhe_da_falha(last_error: str) -> str:
    m = _RE_NOT_READY.search(last_error or '')
    if m:
        presas = int(m.group('presas'))
        sufixo = f' — {presas} impressões presas no Windows' if presas else ''
        return f"{m.group('nome')} não responde{sufixo}"
    if _RE_PRESA.search(last_error or ''):
        return 'A impressora aceitou e não imprimiu (ficou presa no Windows)'
    return 'A impressora não respondeu'


def _e_falha_da_impressora(last_error: str) -> bool:
    return any(sinal in (last_error or '') for sinal in _SINAIS_DE_IMPRESSORA)


def situacao_do_agente(agent, agora=None) -> Situacao:
    from apps.stores.models import StorePrintJob

    agora = agora or timezone.now()

    if not agent.last_seen_at:
        return Situacao('offline', agent.created_at, 'O programa de impressão nunca conectou')
    if agora - agent.last_seen_at > OFFLINE_APOS:
        return Situacao(
            'offline', agent.last_seen_at,
            f'O programa de impressão não responde há {_minutos(agora - agent.last_seen_at)} min',
        )

    jobs = StorePrintJob.objects.filter(claimed_by=agent)
    ultimo_sucesso = (
        jobs.filter(status=StorePrintJob.JobStatus.COMPLETED, printed_at__isnull=False)
        .order_by('-printed_at').values_list('printed_at', flat=True).first()
    )
    falhas = jobs.filter(failed_at__isnull=False).order_by('failed_at')
    if ultimo_sucesso:
        falhas = falhas.filter(failed_at__gt=ultimo_sucesso)
    falhas = [f for f in falhas.only('failed_at', 'last_error') if _e_falha_da_impressora(f.last_error)]
    if not falhas:
        return OK
    return Situacao('impressora_indisponivel', falhas[0].failed_at, _detalhe_da_falha(falhas[-1].last_error))


def _tupla(versao: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r'\d+', versao or ''))


def versao_desatualizada(versao: str) -> bool:
    """Compara número a número: '0.10.0' é mais nova que '0.9.0'."""
    return _tupla(versao) < _tupla(VERSAO_ATUAL_DO_AGENT)
