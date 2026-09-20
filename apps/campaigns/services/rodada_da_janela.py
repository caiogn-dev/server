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
