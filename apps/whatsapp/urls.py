"""
WhatsApp API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import WhatsAppAccountViewSet, MessageViewSet, MessageTemplateViewSet
from .api.intent_views import (
    IntentStatsViewSet,
    IntentLogViewSet,
    AutomationDashboardViewSet,
    AutomationSettingsViewSet,
)

router = DefaultRouter()
router.register(r'accounts', WhatsAppAccountViewSet, basename='whatsapp-account')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'templates', MessageTemplateViewSet, basename='message-template')

# Intent Detection URLs
router.register(r'intents', IntentStatsViewSet, basename='intent-stats')
router.register(r'intents/logs', IntentLogViewSet, basename='intent-log')

# Automation Dashboard URLs
router.register(r'automation/dashboard', AutomationDashboardViewSet, basename='automation-dashboard')
router.register(r'automation/settings', AutomationSettingsViewSet, basename='automation-settings')

urlpatterns = [
    path('', include(router.urls)),
]
