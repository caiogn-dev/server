"""Quem roda os vigias: decide o turno, filtra o que já foi dito e manda UMA mensagem.

O beat chama `tick()` a cada 10 minutos. Ele não decide nada sobre os dados
(isso é das regras); só responde "é hora deste turno nesta loja?". A trava de
"uma mensagem por turno por dia" é uma restrição única no banco
(`VigiaEnvio`), não um lock em memória: beat em dobro, retry ou dois workers
batem na mesma linha e só um passa.
"""
from __future__ import annotations

import logging
from datetime import time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.stores.vigias import canal_do_dono
from apps.stores.vigias.regras import REGRAS_DA_MANHA, Fato, dia_curto, sem_pedido_hoje

logger = logging.getLogger(__name__)

#: Teto de itens na mensagem. O resto fica no painel.
MAXIMO_DE_ITENS = 3
#: Depois disso o resumo "da manhã" já não faz sentido: fica para amanhã.
FIM_DO_TURNO_DA_MANHA = time(20, 0)
#: Depois disso o alerta de "nenhum pedido" não ajuda mais (ver regras).
FIM_DO_TURNO_DE_ALERTA = time(15, 0)


def _local(agora):
    return timezone.localtime(agora or timezone.now())


# ── decidir ───────────────────────────────────────────────────────────────

def _fatos_da_manha(loja, config, agora) -> list[Fato]:
    fatos = []
    for tipo, regra in REGRAS_DA_MANHA:
        if config is not None and not config.tipo_ligado(tipo):
            continue
        try:
            fatos.extend(regra(loja, agora))
        except Exception:  # noqa: BLE001 — uma regra quebrada não cala as outras
            logger.exception('[vigia] regra %s falhou na loja %s', tipo, loja.id)
    return fatos


def _fatos_de_alerta(loja, config, agora) -> list[Fato]:
    if not config.tipo_ligado('sem_pedido'):
        return []
    try:
        return sem_pedido_hoje(loja, agora, hora_alerta=config.hora_alerta)
    except Exception:  # noqa: BLE001
        logger.exception('[vigia] regra sem_pedido falhou na loja %s', loja.id)
        return []


def _ainda_nao_dito(loja, fatos: list[Fato], agora) -> list[Fato]:
    """Tira o que já virou aviso (mesma chave) ou que está no intervalo do assunto."""
    from apps.stores.models import VigiaAviso

    ditos = set(VigiaAviso.objects.filter(store=loja, chave__in=[f.chave for f in fatos])
                .values_list('chave', flat=True))
    novos, vistos = [], set()
    for fato in fatos:
        if fato.chave in ditos or fato.chave in vistos:
            continue
        if fato.intervalo_dias and VigiaAviso.objects.filter(
                store=loja, grupo=fato.grupo,
                criado_em__gte=agora - timedelta(days=fato.intervalo_dias)).exists():
            continue
        vistos.add(fato.chave)
        novos.append(fato)
    return novos


def previa(loja, agora=None) -> list[Fato]:
    """O que a manhã diria agora, sem gravar nem enviar (botão "Ver prévia")."""
    from apps.stores.models import VigiaConfig

    agora = _local(agora)
    config = VigiaConfig.objects.filter(store=loja).first()
    fatos = _fatos_da_manha(loja, config, agora)
    if config is not None and config.tipo_ligado('sem_pedido'):
        fatos += sem_pedido_hoje(loja, agora, hora_alerta=config.hora_alerta)
    return sorted(_ainda_nao_dito(loja, fatos, agora), key=lambda f: -f.prioridade)


# ── compor ────────────────────────────────────────────────────────────────

def compor(loja, turno: str, dia, principais: list, extras: int) -> tuple[str, str]:
    """(texto com quebras para a conversa aberta, linha única para o modelo)."""
    cabecalho = (f'⚠️ *Alerta da {loja.name}*' if turno == 'alerta'
                 else f'📊 *Vigia da {loja.name}* — {dia_curto(dia)}')
    linhas = [cabecalho, ''] + [f'• {a.texto}' for a in principais]
    if extras:
        linhas += ['', f'+{extras} {"aviso" if extras == 1 else "avisos"} no painel.']
    linhas += ['', '_Para pausar, responda PARAR AVISOS._']
    linha = ' • '.join(a.texto for a in principais)
    if extras:
        linha += f' • +{extras} no painel'
    return '\n'.join(linhas), linha


# ── executar ──────────────────────────────────────────────────────────────

def rodar_turno(loja, config, agora, turno: str):
    """Roda um turno numa loja. Devolve o `VigiaEnvio` criado, ou None se o turno já tinha sido feito."""
    from apps.stores.models import VigiaAviso, VigiaEnvio

    agora = _local(agora)
    hoje = agora.date()
    if VigiaEnvio.objects.filter(store=loja, dia=hoje, turno=turno).exists():
        return None

    fatos = _fatos_de_alerta(loja, config, agora) if turno == 'alerta' else _fatos_da_manha(loja, config, agora)
    novos = _ainda_nao_dito(loja, fatos, agora)

    avisos = []
    try:
        with transaction.atomic():
            # A linha do envio é a trava do turno: quem chegar depois cai no IntegrityError.
            envio = VigiaEnvio.objects.create(
                store=loja, dia=hoje, turno=turno, status=VigiaEnvio.Status.SILENCIO,
                telefone=config.telefone,
            )
            for fato in novos:
                try:
                    with transaction.atomic():
                        avisos.append(VigiaAviso.objects.create(
                            store=loja, tipo=fato.tipo, chave=fato.chave, grupo=fato.grupo,
                            prioridade=fato.prioridade, titulo=fato.titulo[:120], texto=fato.texto[:400],
                            dados=fato.dados, envio=envio,
                        ))
                except IntegrityError:
                    continue  # outra execução gravou o mesmo fato no meio do caminho
    except IntegrityError:
        return None

    if not avisos:
        return envio

    avisos.sort(key=lambda a: -a.prioridade)
    principais, extras = avisos[:MAXIMO_DE_ITENS], max(0, len(avisos) - MAXIMO_DE_ITENS)
    texto, linha = compor(loja, turno, hoje, principais, extras)

    # Marca antes de chamar a Meta: se o processo morrer no meio, o turno fica
    # registrado como falho, e não tentado de novo às cegas a cada 10 minutos.
    VigiaEnvio.objects.filter(pk=envio.pk).update(
        status=VigiaEnvio.Status.FALHOU, texto=texto, erro='Interrompido antes do envio.')
    entrega = canal_do_dono.entregar(loja, config.telefone, texto, linha)
    VigiaEnvio.objects.filter(pk=envio.pk).update(
        status=entrega.status, canal=entrega.canal, mensagem_id=entrega.mensagem_id, erro=entrega.erro)
    envio.refresh_from_db()
    logger.info('[vigia] loja %s turno %s: %d avisos, %s por %s', loja.id, turno, len(avisos),
                entrega.status, entrega.canal)
    return envio


def _turnos_devidos(config, agora) -> list[str]:
    if agora.weekday() not in (config.dias or []):
        return []
    hora = agora.time()
    turnos = []
    if config.hora_resumo <= hora < FIM_DO_TURNO_DA_MANHA:
        turnos.append('manha')
    if config.tipo_ligado('sem_pedido') and config.hora_alerta <= hora < FIM_DO_TURNO_DE_ALERTA:
        turnos.append('alerta')
    return turnos


def tick(agora=None) -> int:
    """Passa por todas as lojas com vigia ligado. Devolve quantos turnos rodou."""
    from apps.stores.models import VigiaConfig

    agora = _local(agora)
    rodados = 0
    for config in VigiaConfig.objects.filter(ativo=True, pausado_em__isnull=True).select_related('store'):
        loja = config.store
        if not getattr(loja, 'is_active', True):
            continue
        for turno in _turnos_devidos(config, agora):
            try:
                if rodar_turno(loja, config, agora, turno) is not None:
                    rodados += 1
            except Exception:  # noqa: BLE001 — uma loja não derruba as outras
                logger.exception('[vigia] turno %s falhou na loja %s', turno, loja.id)
    return rodados
