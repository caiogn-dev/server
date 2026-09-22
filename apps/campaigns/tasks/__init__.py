"""
Celery tasks for campaigns.

NOTE: process_scheduled_messages has been moved to apps.automation.tasks.scheduled
to avoid duplication. The unified ScheduledMessage model is in apps.automation.models.
"""
from celery import shared_task
import logging

from django.utils import timezone
import time

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_campaign(self, campaign_id: str):
    """Process a campaign batch."""
    from ..services import CampaignService
    from ..models import Campaign
    
    logger.info(f"Starting to process campaign {campaign_id}")
    
    try:
        service = CampaignService()
        
        # Verify campaign exists and is running
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.status != Campaign.CampaignStatus.RUNNING:
                logger.warning(f"Campaign {campaign_id} is not running (status: {campaign.status})")
                return {'status': 'skipped', 'reason': f'Campaign status is {campaign.status}'}
        except Campaign.DoesNotExist:
            logger.error(f"Campaign {campaign_id} not found")
            return {'status': 'error', 'reason': 'Campaign not found'}
        
        total_processed = 0
        total_failed = 0
        
        while True:
            result = service.process_campaign_batch(campaign_id, batch_size=50)
            
            total_processed += result.get('processed', 0)
            
            if result['remaining'] == 0:
                logger.info(f"Campaign {campaign_id} completed. Total processed: {total_processed}")
                break
            
            logger.info(f"Campaign {campaign_id}: processed {result['processed']}, remaining {result['remaining']}")
            
            # Small delay between batches to avoid rate limiting
            time.sleep(1)
        
        return {
            'status': 'completed',
            'campaign_id': campaign_id,
            'total_processed': total_processed,
        }
        
    except Exception as e:
        logger.error(f"Error processing campaign {campaign_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


@shared_task
def check_scheduled_campaigns():
    """Duas famílias de campanha, dois caminhos.

    Com modelo aprovado (template): continua virando RUNNING no horário marcado.
    Texto livre (marcada como "só janela aberta"): roda o DIA INTEIRO, porque o
    horário de cada pessoa pode ser ANTES do horário da campanha — é assim que
    quem fecharia a janela às 12h recebe às 11h em vez de ser descartado.
    """
    from zoneinfo import ZoneInfo

    from ..models import Campaign
    from ..services.janela import fuso_da_campanha
    from ..services import rodada_da_janela

    rodada_da_janela.liberar_reservas_presas()
    agora = timezone.now()

    marcadas = list(
        Campaign.objects.filter(
            status__in=[Campaign.CampaignStatus.SCHEDULED, Campaign.CampaignStatus.RUNNING],
            is_active=True,
            audience_filters__somente_janela_aberta=True,
        ).exclude(scheduled_at=None)
    )
    for campanha in marcadas:
        zona = ZoneInfo(fuso_da_campanha(campanha))
        # Só no dia dela: o alvo de cada pessoa nasce do horário da campanha.
        if campanha.scheduled_at.astimezone(zona).date() != agora.astimezone(zona).date():
            continue
        rodada_da_janela.processar_rodada_da_janela(campanha, agora=agora)

    # `exclude(audience_filters__chave=True)` descartaria também quem NÃO tem a
    # chave (no SQL, NOT NULL é NULL) — some com toda campanha de template.
    antigas = Campaign.objects.filter(
        status=Campaign.CampaignStatus.SCHEDULED,
        scheduled_at__lte=agora,
        is_active=True,
    ).exclude(id__in=[c.id for c in marcadas])
    for campaign in antigas:
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.started_at = agora
        campaign.save()

        process_campaign.delay(str(campaign.id))
        logger.info(f"Started scheduled campaign: {campaign.id}")
