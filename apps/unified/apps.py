from django.apps import AppConfig


class UnifiedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.unified'
    verbose_name = 'Unified APIs'
