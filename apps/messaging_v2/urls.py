"""
URLs para messaging_v2 - API REST completa.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from . import webhooks

router = DefaultRouter()
router.register(r'platform-accounts', views.PlatformAccountViewSet, basename='platform-account')
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.UnifiedMessageViewSet, basename='message')
router.register(r'templates', views.MessageTemplateViewSet, basename='template')

urlpatterns = [
    # API REST
    path('', include(router.urls)),
    
    # Webhooks
    path('webhooks/whatsapp/', webhooks.whatsapp_webhook, name='whatsapp-webhook'),
    path('webhooks/instagram/', webhooks.instagram_webhook, name='instagram-webhook'),
    path('webhooks/<str:platform>/', webhooks.generic_webhook, name='generic-webhook'),
]
