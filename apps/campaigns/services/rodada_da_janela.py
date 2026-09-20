"""A rodada do agendador: quem recebe agora, sem mandar duas vezes.

A campanha de texto livre só chega de graça a quem falou com a loja nas
últimas 24 h. A rodada roda de minuto em minuto e vai soltando cada
destinatário quando a janela DELE abre — por isso o mesmo destinatário pode
cair em duas rodadas, e a reserva é o que impede a mensagem dupla.
"""
from datetime import timedelta

from django.utils import timezone


def reservar(recipient_id) -> bool:
    """Pega o destinatário para esta rodada. True = esta rodada envia.

    UPDATE condicional, não ler-e-gravar: entre ler e gravar cabe outra rodada,
    e o cliente receberia a mesma promoção duas vezes.
    """
    from apps.campaigns.models import CampaignRecipient

    # `.update()` não dispara o auto_now de updated_at — o carimbo vai à mão,
    # e é ele que diz há quanto tempo a reserva está presa.
    return CampaignRecipient.objects.filter(
        id=recipient_id, status=CampaignRecipient.RecipientStatus.PENDING,
    ).update(
        status=CampaignRecipient.RecipientStatus.SENDING,
        updated_at=timezone.now(),
    ) == 1


def liberar_reservas_presas(minutos: int = 10) -> int:
    """`sending` velho = worker morreu no meio. Volta para a fila."""
    from apps.campaigns.models import CampaignRecipient

    return CampaignRecipient.objects.filter(
        status=CampaignRecipient.RecipientStatus.SENDING,
        updated_at__lt=timezone.now() - timedelta(minutes=minutos),
    ).update(status=CampaignRecipient.RecipientStatus.PENDING, updated_at=timezone.now())


def _pular(destinatario, codigo: str) -> None:
    """`skipped`, não `failed`: não deu para mandar, mas nada quebrou."""
    from apps.campaigns.models import CampaignRecipient

    destinatario.status = CampaignRecipient.RecipientStatus.SKIPPED
    destinatario.error_code = codigo
    destinatario.save(update_fields=['status', 'error_code', 'updated_at'])


def processar_rodada_da_janela(campaign, agora=None) -> dict:
    """Uma foto do momento: envia para quem já chegou a hora.

    Nada é agendado por pessoa — o alvo é recalculado a cada rodada porque a
    janela se move: quem responder ao bot às 15h renova a dele e passa a caber
    no horário da campanha.
    """
    from apps.campaigns.models import Campaign, CampaignRecipient
    from apps.campaigns.services.campaign_service import CampaignService
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.campaigns.services.janela import (
        fechamentos_por_chave, fuso_da_campanha, horario_alvo,
    )
    from apps.campaigns.services.motivos import FORA_DA_JANELA, PEDIU_PARA_PARAR
    from apps.campaigns.services.optout import chaves_bloqueadas
    from apps.whatsapp.tasks import acquire_lock, release_lock

    agora = agora or timezone.now()
    parado = {'enviados': 0, 'aguardando': 0, 'pulados': 0, 'concluida': False}
    if campaign.status not in (Campaign.CampaignStatus.SCHEDULED, Campaign.CampaignStatus.RUNNING):
        return parado
    if not campaign.scheduled_at:
        return parado
    # Duas rodadas na mesma campanha ao mesmo tempo passariam o teto de envio.
    if not acquire_lock(f'campanha:{campaign.id}', timeout=120):
        return parado

    try:
        fuso = fuso_da_campanha(campaign)
        fechamentos = fechamentos_por_chave([campaign.account_id])
        bloqueadas = chaves_bloqueadas(campaign.account)
        teto = max(1, campaign.messages_per_minute or 60)
        servico = CampaignService()

        enviados = aguardando = pulados = 0
        for destinatario in campaign.recipients.filter(
            status=CampaignRecipient.RecipientStatus.PENDING,
        ):
            chave = chave_do_telefone(destinatario.phone_number)
            if chave in bloqueadas:
                _pular(destinatario, PEDIU_PARA_PARAR)
                pulados += 1
                continue

            alvo = horario_alvo(fechamentos.get(chave), campaign.scheduled_at, fuso)
            if alvo is None:
                # Só desiste depois que o horário da campanha passou: até lá a
                # pessoa ainda pode responder à loja e reabrir a janela dela.
                if agora >= campaign.scheduled_at:
                    _pular(destinatario, FORA_DA_JANELA)
                    pulados += 1
                else:
                    aguardando += 1
                continue

            if alvo > agora or enviados >= teto:
                aguardando += 1
                continue

            if not reservar(destinatario.id):
                continue
            if servico.enviar_para(campaign, destinatario):
                enviados += 1
            else:
                pulados += 1

        if enviados and campaign.status != Campaign.CampaignStatus.RUNNING:
            campaign.status = Campaign.CampaignStatus.RUNNING
            campaign.started_at = campaign.started_at or agora
            campaign.save(update_fields=['status', 'started_at', 'updated_at'])

        concluida = agora >= campaign.scheduled_at and aguardando == 0 and not (
            campaign.recipients.filter(status=CampaignRecipient.RecipientStatus.SENDING).exists()
        )
        if concluida and campaign.status == Campaign.CampaignStatus.RUNNING:
            campaign.status = Campaign.CampaignStatus.COMPLETED
            campaign.completed_at = agora
            campaign.save(update_fields=['status', 'completed_at', 'updated_at'])

        return {'enviados': enviados, 'aguardando': aguardando,
                'pulados': pulados, 'concluida': concluida}
    finally:
        release_lock(f'campanha:{campaign.id}')
