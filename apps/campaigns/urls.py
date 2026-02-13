"""
Campaign API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import CampaignViewSet, ScheduledMessageViewSet, ContactListViewSet
from .api.views import SystemContactsView

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'scheduled', ScheduledMessageViewSet, basename='scheduled-message')
router.register(r'contacts', ContactListViewSet, basename='contact-list')

urlpatterns = [
    path('system-contacts/', SystemContactsView.as_view(), name='system-contacts'),
    path('', include(router.urls)),
]
