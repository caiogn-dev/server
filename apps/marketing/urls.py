"""
Marketing URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    EmailTemplateViewSet,
    EmailCampaignViewSet,
    SubscriberViewSet,
    CustomersViewSet,
    MarketingStatsViewSet,
    QuickActionsViewSet,
    EmailAutomationViewSet,
    TemplateVariablesViewSet,
)

router = DefaultRouter()
router.register(r'templates', EmailTemplateViewSet, basename='email-templates')
router.register(r'campaigns', EmailCampaignViewSet, basename='email-campaigns')
router.register(r'subscribers', SubscriberViewSet, basename='subscribers')
router.register(r'customers', CustomersViewSet, basename='customers')
router.register(r'automations', EmailAutomationViewSet, basename='email-automations')
router.register(r'stats', MarketingStatsViewSet, basename='marketing-stats')
router.register(r'actions', QuickActionsViewSet, basename='quick-actions')
router.register(r'variables', TemplateVariablesViewSet, basename='template-variables')

urlpatterns = [
    path('', include(router.urls)),
]
