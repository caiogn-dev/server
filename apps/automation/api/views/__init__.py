"""
Automation API views - organized by domain.

This module exports all viewsets from their respective domain modules.
"""

# Import from base module
from .base import StandardResultsSetPagination

# Import company profile views
from .company_profile_views import CompanyProfileViewSet

# Import auto message views
from .auto_message_views import AutoMessageViewSet

# Import customer session views
from .customer_session_views import CustomerSessionViewSet

# Import automation log views
from .automation_log_views import AutomationLogViewSet

# Import scheduled message views
from .scheduled_message_views import ScheduledMessageViewSet

# Import report views
from .report_views import ReportScheduleViewSet, GeneratedReportViewSet

__all__ = [
    'StandardResultsSetPagination',
    'CompanyProfileViewSet',
    'AutoMessageViewSet',
    'CustomerSessionViewSet',
    'AutomationLogViewSet',
    'ScheduledMessageViewSet',
    'ReportScheduleViewSet',
    'GeneratedReportViewSet',
]
