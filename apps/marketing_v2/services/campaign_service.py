"""Campaign Service for Marketing v2."""

from datetime import datetime
from django.db import transaction
from ..models import Campaign, Template


class CampaignService:
    """Service for campaign management."""

    @staticmethod
    def create_campaign(store, name, channel='whatsapp', **kwargs):
        """Create a new campaign."""
        campaign = Campaign.objects.create(
            store=store,
            name=name,
            channel=channel,
            **kwargs
        )
        return campaign

    @staticmethod
    def schedule_campaign(campaign_id, scheduled_at):
        """Schedule a campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        campaign.status = Campaign.Status.SCHEDULED
        campaign.scheduled_at = scheduled_at
        campaign.save(update_fields=['status', 'scheduled_at'])
        return campaign

    @staticmethod
    def send_campaign(campaign_id):
        """Mark campaign as sending/completed."""
        campaign = Campaign.objects.get(id=campaign_id)
        campaign.status = Campaign.Status.SENDING
        campaign.save(update_fields=['status'])
        return campaign
