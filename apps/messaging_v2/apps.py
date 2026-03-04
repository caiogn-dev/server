"""
Django AppConfig for messaging_v2.
"""
from django.apps import AppConfig


class MessagingV2Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.messaging_v2'
    verbose_name = 'Messaging (Unified)'

    def ready(self):
        # Import signals if needed
        pass
