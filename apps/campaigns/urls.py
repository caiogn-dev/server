"""
Campaign API URLs - Unified with Automation.

Note: Scheduled messages are now handled by the automation app.
Use /api/v1/automation/scheduled-messages/ for scheduled message operations.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import CampaignViewSet, ContactListViewSet
from .api.views import SystemContactsView

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'contacts', ContactListViewSet, basename='contact-list')

urlpatterns = [
    path('system-contacts/', SystemContactsView.as_view(), name='system-contacts'),
    path('', include(router.urls)),
]
