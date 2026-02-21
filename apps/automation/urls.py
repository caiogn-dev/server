"""
Automation app URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    CompanyProfileViewSet,
    AutoMessageViewSet,
    CustomerSessionViewSet,
    AutomationLogViewSet,
    ScheduledMessageViewSet,
    ReportScheduleViewSet,
    GeneratedReportViewSet,
    AgentFlowViewSet,
    FlowSessionViewSet,
    FlowExecutionLogViewSet,
)

router = DefaultRouter()
router.register(r'companies', CompanyProfileViewSet, basename='company-profile')
router.register(r'messages', AutoMessageViewSet, basename='auto-message')
router.register(r'sessions', CustomerSessionViewSet, basename='customer-session')
router.register(r'logs', AutomationLogViewSet, basename='automation-log')
router.register(r'scheduled-messages', ScheduledMessageViewSet, basename='scheduled-message')
router.register(r'report-schedules', ReportScheduleViewSet, basename='report-schedule')
router.register(r'reports', GeneratedReportViewSet, basename='generated-report')
# Flow Builder endpoints
router.register(r'flows', AgentFlowViewSet, basename='agent-flow')
router.register(r'flow-sessions', FlowSessionViewSet, basename='flow-session')
router.register(r'flow-logs', FlowExecutionLogViewSet, basename='flow-execution-log')

urlpatterns = [
    path('', include(router.urls)),
]
