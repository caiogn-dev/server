"""
Celery tasks for campaigns.

NOTE: process_scheduled_messages has been moved to apps.automation.tasks.scheduled
to avoid duplication. The unified ScheduledMessage model is in apps.automation.models.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def process_campaign(campaign_id: str):
    """Process a campaign batch."""
    from ..services import CampaignService
    
    service = CampaignService()
    
    while True:
        result = service.process_campaign_batch(campaign_id, batch_size=100)
        
        if result['remaining'] == 0:
            logger.info(f"Campaign {campaign_id} completed")
            break
        
        logger.info(f"Campaign {campaign_id}: processed {result['processed']}, remaining {result['remaining']}")


@shared_task
def check_scheduled_campaigns():
    """Check and start scheduled campaigns."""
    from django.utils import timezone
    from ..models import Campaign
    
    campaigns = Campaign.objects.filter(
        status=Campaign.CampaignStatus.SCHEDULED,
        scheduled_at__lte=timezone.now(),
        is_active=True,
    )
    
    for campaign in campaigns:
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.started_at = timezone.now()
        campaign.save()
        
        process_campaign.delay(str(campaign.id))
        logger.info(f"Started scheduled campaign: {campaign.id}")
