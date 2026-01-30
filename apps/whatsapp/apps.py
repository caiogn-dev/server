from django.apps import AppConfig
from django.db.models.signals import post_migrate


class WhatsAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.whatsapp'
    label = 'whatsapp'

    def ready(self):
        from .startup import ensure_default_whatsapp_account

        post_migrate.connect(
            ensure_default_whatsapp_account,
            sender=self,
            weak=False,
        )
