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

O aviso ao dono sai UMA vez por episódio (e uma quando volta), pelo WhatsApp
da loja para o telefone de alerta — nunca a cada rodada do vigia. O painel lê
a mesma situação pelo serializer do agente.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.utils import normalize_phone_number

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


def _numero_da_conta(conta) -> str:
    return normalize_phone_number(getattr(conta, 'display_phone_number', '') or getattr(conta, 'phone_number', '') or '')


def telefone_de_alerta(store, *, numero_da_conta: str) -> str | None:
    """Para quem avisar: o telefone de alerta da loja, senão o telefone da loja.

    Nunca o próprio número do WhatsApp da loja — na Cê Saladas o telefone da
    loja É a conta, e mandar para ele seria falar sozinho.
    """
    metadata = store.metadata if isinstance(store.metadata, dict) else {}
    bruto = (metadata.get('telefone_de_alerta') or '').strip() or (store.phone or '')
    telefone = normalize_phone_number(bruto)
    if not telefone or telefone == normalize_phone_number(numero_da_conta):
        return None
    return telefone


def enviar_texto_para_a_loja(conta, telefone: str, texto: str, evento: str):
    """Aviso operacional para a LOJA, não para cliente: não passa pela política
    do modo humano (o dono estar atendendo alguém não é motivo para calar o
    aviso de que a cozinha parou de imprimir). Grava como automática, como
    tudo que sai do canal."""
    from apps.automation.mensageiro import canal

    return canal._enviar(lambda: _service().send_text_message(  # noqa: SLF001 — mesmo canal, sem a política
        account_id=str(conta.id), to=telefone, text=texto, metadata=canal._meta(evento),
    ))


def _service():
    from apps.whatsapp.services.message_service import MessageService

    return MessageService()


def _texto_parada(agent, situacao: Situacao) -> str:
    hora = timezone.localtime(situacao.desde).strftime('%H:%M') if situacao.desde else ''
    desde = f' desde {hora}' if hora else ''
    return (
        f'⚠️ Impressora *{agent.name}* da {agent.store.name} parada{desde}.\n'
        f'{situacao.detalhe}.\n\n'
        'Os pedidos continuam entrando no painel; a comanda não está saindo na cozinha. '
        'Confira se a impressora está ligada e o cabo conectado.'
    )


def _texto_voltou(agent) -> str:
    return f'✅ Impressora *{agent.name}* da {agent.store.name} voltou a imprimir.'


def vigiar_agente(agent, agora=None) -> Situacao:
    """Confere a situação e avisa o dono na MUDANÇA — uma vez por episódio."""
    agora = agora or timezone.now()
    situacao = situacao_do_agente(agent, agora=agora)
    metadata = agent.metadata if isinstance(agent.metadata, dict) else {}
    alerta = metadata.get('alerta') or {}
    episodio = situacao.desde.isoformat() if situacao.desde else ''

    if situacao.parada:
        mesmo_episodio = alerta.get('codigo') == situacao.codigo and alerta.get('desde') == episodio
        if mesmo_episodio and alerta.get('avisado_em'):
            return situacao
        novo = {'codigo': situacao.codigo, 'desde': episodio, 'detalhe': situacao.detalhe}
        if _avisar(agent, _texto_parada(agent, situacao), 'impressora_parada'):
            novo['avisado_em'] = agora.isoformat()
        metadata['alerta'] = novo
    else:
        if not alerta:
            return situacao
        _avisar(agent, _texto_voltou(agent), 'impressora_voltou')
        metadata.pop('alerta', None)

    agent.metadata = metadata
    agent.save(update_fields=['metadata', 'updated_at'])
    return situacao


def _avisar(agent, texto: str, evento: str) -> bool:
    from apps.automation.mensageiro.canal import EnvioFalhou

    conta = agent.store.get_whatsapp_account()
    if not conta:
        return False
    telefone = telefone_de_alerta(agent.store, numero_da_conta=_numero_da_conta(conta))
    if not telefone:
        return False
    try:
        enviar_texto_para_a_loja(conta, telefone, texto, evento)
    except EnvioFalhou as exc:
        logger.warning('Aviso de impressora (%s) não saiu para %s: %s', evento, agent.store.slug, exc)
        return False
    return True


def vigiar_todos(agora=None) -> dict[str, int]:
    from apps.stores.models import StorePrintAgent

    contagem: dict[str, int] = {}
    for agent in StorePrintAgent.objects.filter(is_active=True, status=StorePrintAgent.AgentStatus.ACTIVE).select_related('store'):
        try:
            situacao = vigiar_agente(agent, agora=agora)
        except Exception:  # noqa: BLE001 — um agente com problema não cala os outros
            logger.exception('Vigia falhou no agente %s', agent.id)
            continue
        contagem[situacao.codigo] = contagem.get(situacao.codigo, 0) + 1
    return contagem
