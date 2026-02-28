"""
DEPRECATED: This app is deprecated and will be removed in a future version.

The canonical Messenger implementation is in apps.messaging.
This app is kept temporarily for backward compatibility.

Migration path:
- Use apps.messaging.models.MessengerAccount instead of apps.messenger.models.MessengerAccount
- Use apps.messaging.models.MessengerConversation instead of apps.messenger.models.MessengerConversation
- Use apps.messaging.models.MessengerMessage instead of apps.messenger.models.MessengerMessage

All new code should use apps.messaging.
"""
from django.apps import AppConfig


class MessengerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.messenger'
    verbose_name = 'Messenger Platform (DEPRECATED - use apps.messaging)'
