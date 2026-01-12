"""
Campaign API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import CampaignViewSet, ScheduledMessageViewSet, ContactListViewSet

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'scheduled', ScheduledMessageViewSet, basename='scheduled-message')
router.register(r'contacts', ContactListViewSet, basename='contact-list')

urlpatterns = [
    path('', include(router.urls)),
]
