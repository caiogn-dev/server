"""
WhatsApp webhook URLs.
"""
from django.urls import path
from .views import WhatsAppWebhookView, WebhookDebugView

urlpatterns = [
    path('', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('debug/', WebhookDebugView.as_view(), name='whatsapp-webhook-debug'),
]
