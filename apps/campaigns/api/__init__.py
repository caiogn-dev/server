"""
Campaign API - Unified with Automation.

Note: ScheduledMessageViewSet has been moved to apps.automation.api.
Use /api/v1/automation/scheduled-messages/ for scheduled message operations.
"""
from .views import CampaignViewSet, ContactListViewSet
from .serializers import (
    CampaignSerializer,
    CampaignCreateSerializer,
    CampaignRecipientSerializer,
    ContactListSerializer,
)

__all__ = [
    'CampaignViewSet',
    'ContactListViewSet',
    'CampaignSerializer',
    'CampaignCreateSerializer',
    'CampaignRecipientSerializer',
    'ContactListSerializer',
]
