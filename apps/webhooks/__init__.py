"""
Webhooks App - Centralized webhook handling.

This app provides a unified entrypoint for all webhooks:
- WhatsApp webhooks from Meta
- Instagram webhooks from Meta
- Payment webhooks from Mercado Pago
- Automation webhooks

All webhooks are routed through /webhooks/v1/{provider}/
"""

default_app_config = 'apps.webhooks.apps.WebhooksConfig'
