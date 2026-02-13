# Instagram App Config
from django.apps import AppConfig


class InstagramConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.instagram'
    label = 'instagram'
    
    def ready(self):
        import apps.instagram.signals  # noqa
