"""
Webhook URLs - Centralized webhook routing.

All webhooks are routed through:
- /webhooks/v1/{provider}/ - Main webhook endpoint
- /webhooks/v1/{provider}/verify/ - Verification endpoint (if needed)
"""
from django.urls import path
from .dispatcher import WebhookDispatcherView

urlpatterns = [
    # Main webhook endpoint for all providers
    path('<str:provider>/', WebhookDispatcherView.as_view(), name='webhook_receiver'),
]
