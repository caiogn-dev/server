"""
Core v2 - App configuration.
"""
from django.apps import AppConfig


class CoreV2Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core_v2'
    verbose_name = 'Core (v2)'

    def ready(self):
        # Signals desabilitados temporariamente para migração
        # import apps.core_v2.signals  # noqa
        pass
