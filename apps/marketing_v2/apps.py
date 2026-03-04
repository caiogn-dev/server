from django.apps import AppConfig


class MarketingV2Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.marketing_v2'
    verbose_name = 'Marketing V2'
    
    def ready(self):
        # Import signals if needed
        pass
