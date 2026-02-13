"""
Celery tasks for campaigns.

NOTE: process_scheduled_messages has been moved to apps.automation.tasks.scheduled
to avoid duplication. The unified ScheduledMessage model is in apps.automation.models.
"""
from celery import shared_task
import logging
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
