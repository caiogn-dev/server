from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.automation'
    verbose_name = 'Automation'

    def ready(self):
        """Import signals when app is ready."""
        try:
            import apps.automation.signals  # noqa
        except ImportError:
            pass
