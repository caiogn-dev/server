"""Tarefas da conversa.

`avisar_fila_humana` (beat, 2 min): avisa o telefone da loja quando um
cliente está esperando atendente há mais de N minutos. OPT-IN — o dono não
quer aviso que não pediu (o de impressora foi retirado em 26/09):

    Store.metadata['aviso_fila_humana'] = {"ativo": false, "apos_minutos": 5, "telefone": ""}

Um aviso por espera: a marca fica em `Conversation.context['aviso_fila']`
com o início da espera. Quando alguém responde e o cliente volta a esperar,
é outra espera e pode gerar outro aviso.
"""
import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

EVENTO = 'fila_humana'


def _config(loja) -> dict:
    cfg = (loja.metadata or {}).get('aviso_fila_humana') or {}
    if not isinstance(cfg, dict) or cfg.get('ativo') is not True:
        return {}
    telefone = ''.join(ch for ch in str(cfg.get('telefone') or '') if ch.isdigit())
    if not telefone:
        return {}
    try:
        apos = max(1, int(cfg.get('apos_minutos') or 5))
    except (TypeError, ValueError):
        apos = 5
    return {'telefone': telefone, 'apos_minutos': apos}


def _ultima_do_cliente(conversa) -> str:
    from apps.whatsapp.models import Message

    texto = (
        Message.objects.filter(conversation=conversa, direction='inbound')
        .order_by('-created_at').values_list('text_body', flat=True).first()
    ) or ''
    texto = ' '.join(texto.split())
    return texto if len(texto) <= 120 else texto[:117] + '...'


def _enviar(conta, telefone, texto, conversa):
    """Canal do mensageiro; se a política do modo humano calar, direto.

    A política cala automática para conversa em modo humano com AQUELE
    telefone — aqui o destino é o dono, e o aviso existe justamente por causa
    do modo humano.
    """
    from apps.automation.mensageiro import canal

    extra = {'conversa_id': str(conversa.id)}
    enviada = canal.enviar_texto(conta, telefone, texto, evento=EVENTO, extra=extra)
    if enviada is not None:
        return enviada
    from apps.whatsapp.services.message_service import MessageService

    return MessageService().send_text_message(
        account_id=str(conta.id), to=telefone, text=texto,
        metadata={**extra, 'automatico': True, 'evento': EVENTO},
    )


def avisar_loja(loja, cfg, agora) -> int:
    from apps.conversations.models import Conversation
    from apps.conversations.services import operacao_humana as op

    conversas = (
        Conversation.objects.filter(is_active=True, mode=Conversation.ConversationMode.HUMAN)
        .filter(Q(account__stores=loja) | Q(account__company_profile__store=loja))
        .select_related('account').distinct()
    )
    enviados = 0
    for conversa in conversas:
        desde = op.esperando_desde(conversa)
        if desde is None:
            continue
        minutos = op.segundos_desde(desde, agora) // 60
        if minutos < cfg['apos_minutos']:
            continue
        marca = (conversa.context or {}).get('aviso_fila') or {}
        if marca.get('esperando_desde') == desde.isoformat():
            continue
        texto = (
            f"⏳ {op.nome_do_cliente(conversa)} está esperando atendimento há {minutos} min "
            f"na {loja.name}. Última mensagem: '{_ultima_do_cliente(conversa)}'"
        )
        erro = ''
        try:
            _enviar(conversa.account, cfg['telefone'], texto, conversa)
            enviados += 1
        except Exception as exc:  # noqa: BLE001 — um aviso não derruba os outros
            erro = str(exc)[:200]
            logger.warning('[fila_humana] aviso não saiu: %s', exc,
                           extra={'conversation_id': str(conversa.id), 'store_id': str(loja.id)})
        # Marca mesmo quando falha: janela de 24h fechada com o dono falharia
        # a cada 2 min, para sempre. Uma tentativa por espera.
        contexto = dict(conversa.context or {})
        contexto['aviso_fila'] = {
            'esperando_desde': desde.isoformat(), 'avisado_em': agora.isoformat(), 'erro': erro,
        }
        Conversation.objects.filter(pk=conversa.pk).update(context=contexto)
    return enviados


@shared_task(name='apps.conversations.tasks.avisar_fila_humana', ignore_result=True)
def avisar_fila_humana() -> int:
    from apps.stores.models import Store

    agora = timezone.now()
    total = 0
    for loja in Store.objects.filter(metadata__aviso_fila_humana__ativo=True):
        cfg = _config(loja)
        if not cfg:
            continue
        try:
            total += avisar_loja(loja, cfg, agora)
        except Exception:  # noqa: BLE001
            logger.exception('[fila_humana] falha ao avisar a loja %s', loja.id)
    return total
