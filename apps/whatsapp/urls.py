"""
WhatsApp API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import WhatsAppAccountViewSet, MessageViewSet, MessageTemplateViewSet

router = DefaultRouter()
router.register(r'accounts', WhatsAppAccountViewSet, basename='whatsapp-account')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'templates', MessageTemplateViewSet, basename='message-template')

urlpatterns = [
    path('', include(router.urls)),
]
