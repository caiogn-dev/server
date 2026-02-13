"""
WhatsApp webhook URLs.

IMPORTANT: Meta's WhatsApp API sends webhooks WITHOUT trailing slash.
We need to handle both cases to avoid 301 redirects that break POST requests.
"""
from django.urls import path, re_path
from .views import WhatsAppWebhookView, WebhookDebugView

urlpatterns = [
    # Handle both with and without trailing slash to avoid 301 redirects
    # Meta sends to /webhooks/whatsapp (no trailing slash)
    path('', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('debug/', WebhookDebugView.as_view(), name='whatsapp-webhook-debug'),
]
