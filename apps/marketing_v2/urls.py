"""
Marketing v2 - URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CampaignViewSet, TemplateViewSet, AutomationViewSet

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet)
router.register(r'templates', TemplateViewSet)
router.register(r'automations', AutomationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
