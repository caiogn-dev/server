"""
Messaging providers package.

Available providers:
- WhatsAppProvider: For WhatsApp Business API messages
- EmailProvider: For email messages (SMTP/API)
- InstagramProvider: For Instagram DM messages
"""

from .base import BaseProvider, ProviderResult
from .whatsapp_provider import WhatsAppProvider
from .email_provider import EmailProvider
from .instagram_provider import InstagramProvider

__all__ = [
    'BaseProvider', 
    'ProviderResult', 
    'WhatsAppProvider', 
    'EmailProvider',
    'InstagramProvider',
]
