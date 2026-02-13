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
)

router = DefaultRouter()
router.register(r'companies', CompanyProfileViewSet, basename='company-profile')
router.register(r'messages', AutoMessageViewSet, basename='auto-message')
router.register(r'sessions', CustomerSessionViewSet, basename='customer-session')
router.register(r'logs', AutomationLogViewSet, basename='automation-log')
router.register(r'scheduled-messages', ScheduledMessageViewSet, basename='scheduled-message')
router.register(r'report-schedules', ReportScheduleViewSet, basename='report-schedule')
router.register(r'reports', GeneratedReportViewSet, basename='generated-report')

urlpatterns = [
    path('', include(router.urls)),
]
