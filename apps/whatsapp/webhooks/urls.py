"""
WhatsApp webhook URLs.
"""
from django.urls import path
from .views import WhatsAppWebhookView

urlpatterns = [
    path('', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
]
