"""
Campaign services - Unified with Automation.

Note: SchedulerService has been replaced by UnifiedMessagingService from automation app.
Use apps.automation.services.UnifiedMessagingService for scheduled message operations.
"""
from .campaign_service import CampaignService

__all__ = ['CampaignService']
