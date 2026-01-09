"""
WSGI config for WhatsApp Business Platform.
"""
import os
from django.core.wsgi import get_wsgi_application

# Use production settings by default if DJANGO_SETTINGS_MODULE is not set
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

application = get_wsgi_application()
