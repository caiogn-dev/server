"""
Automation API views - organized by domain.

This module maintains backward compatibility by re-exporting all views 
from the original views.py file while the modular structure is being built.

Future imports will be organized as:
- company_profile_views.py - CompanyProfileViewSet
- auto_message_views.py - AutoMessageViewSet
- customer_session_views.py - CustomerSessionViewSet
- automation_log_views.py - AutomationLogViewSet
- scheduled_message_views.py - ScheduledMessageViewSet
- report_views.py - ReportScheduleViewSet, GeneratedReportViewSet
"""

# Import from base module (future modular imports)
from .base import StandardResultsSetPagination

# Re-export all from original views.py for backward compatibility
# This allows gradual migration to modular structure
from ..views import (
    CompanyProfileViewSet,
    AutoMessageViewSet,
    CustomerSessionViewSet,
    AutomationLogViewSet,
    ScheduledMessageViewSet,
    ReportScheduleViewSet,
    GeneratedReportViewSet,
)

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
