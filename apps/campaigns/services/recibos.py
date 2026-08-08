"""Leva o recibo de entrega da Meta até os contadores da campanha.

O webhook de status já atualizava `Message`. Faltava o elo até
`CampaignRecipient` — que guarda o MESMO `whatsapp_message_id` — e por isso
`Campaign.messages_delivered` e `messages_read` eram estruturalmente zero:
nenhuma linha do código escrevia neles.

O sintoma só apareceu em 08/ago/2026, quando o painel passou a mostrar entrega
e leitura na linha da campanha: as duas campanhas concluídas da Cê Saladas
apareceram com "0 entregues". A mensagem tinha chegado; o número é que nunca
foi contado.

POR QUE OS CONTADORES SÃO MONOTÔNICOS POR DESTINATÁRIO

A Meta reenvia status (retry, duplicata do webhook, ordem trocada). Somar a
cada recibo produziria 200% de entrega — número impossível que destrói a
confiança na tela inteira. Então quem manda é a TRANSIÇÃO do destinatário:
o contador só sobe quando o destinatário efetivamente avança de estado.
"""
import logging

from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Ordem de progresso. `failed` fica de fora porque não é um estágio adiante:
# é um desfecho, e pode chegar sem nunca ter passado por delivered.
ORDEM = ['pending', 'sent', 'delivered', 'read']


def _posicao(status: str) -> int:
    try:
        return ORDEM.index(status)
    except ValueError:
        return -1


@transaction.atomic
def registrar_recibo(whatsapp_message_id: str, status: str, erro: dict | None = None) -> bool:
    """Aplica um recibo da Meta ao destinatário da campanha.

    Devolve `True` quando algo mudou. `False` cobre o caso COMUM — recibo de
    conversa normal do inbox, que não pertence a campanha nenhuma — e por isso
    não loga warning: encheria o log de ruído e esconderia problema de verdade.
    """
    from apps.campaigns.models import Campaign, CampaignRecipient

    if not whatsapp_message_id or status not in {'delivered', 'read', 'failed'}:
        return False

    destinatario = (
        CampaignRecipient.objects
        .select_for_update()
        .filter(whatsapp_message_id=whatsapp_message_id)
        .first()
    )
    if destinatario is None:
        return False

    agora = timezone.now()
    incrementos: dict[str, int] = {}

    if status == 'failed':
        # Falha já contabilizada não conta de novo.
        if destinatario.status == CampaignRecipient.RecipientStatus.FAILED:
            return False
        destinatario.status = CampaignRecipient.RecipientStatus.FAILED
        destinatario.failed_at = agora
        if erro:
            destinatario.error_code = str(erro.get('code', ''))
            # Sem o motivo, "1 falha" não diz se foi número errado ou janela de
            # 24h — e são ações opostas para quem opera.
            destinatario.error_message = erro.get('title', '') or erro.get('message', '')
        incrementos['messages_failed'] = 1
        destinatario.save(update_fields=[
            'status', 'failed_at', 'error_code', 'error_message', 'updated_at',
        ])
    else:
        atual = _posicao(destinatario.status)
        novo = _posicao(status)
        # Webhook fora de ordem: `delivered` chegando depois de `read` não pode
        # rebaixar o destinatário nem somar outra vez.
        if novo <= atual:
            return False

        campos = ['status', 'updated_at']

        # A Meta às vezes manda só o `read` (leitura rápida, ou o `delivered`
        # se perdeu). Sem contar a entrega implícita, a campanha mostraria mais
        # lidas do que entregues — impossível, e o operador para de acreditar.
        if atual < _posicao('delivered'):
            incrementos['messages_delivered'] = 1
            destinatario.delivered_at = agora
            campos.append('delivered_at')

        if status == 'read':
            incrementos['messages_read'] = 1
            destinatario.read_at = agora
            campos.append('read_at')

        destinatario.status = (
            CampaignRecipient.RecipientStatus.READ
            if status == 'read'
            else CampaignRecipient.RecipientStatus.DELIVERED
        )
        destinatario.save(update_fields=campos)

    if incrementos:
        # F() em vez de ler-somar-gravar: dois recibos concorrentes no mesmo
        # segundo perderiam uma contagem.
        Campaign.objects.filter(id=destinatario.campaign_id).update(**{
            campo: models.F(campo) + valor for campo, valor in incrementos.items()
        })

    return True
