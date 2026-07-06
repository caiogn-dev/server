"""
Configurações mínimas para testes de serializer sem Docker/daphne/Redis/Postgres.
Usado pelo bot de revisão automática para rodar SimpleTestCase unit tests.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = 'test-only-secret-key-not-for-production'
DEBUG = True

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'rest_framework',
    'rest_framework.authtoken',
    'apps.core',
    'apps.stores',
    'apps.whatsapp.apps.WhatsAppConfig',
    'apps.automation',
    'apps.conversations',
    'apps.campaigns',
    'apps.audit',
    'apps.messaging',
    'apps.webhooks',
    'apps.handover',
    'apps.users',
    'apps.public_api',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# Celery — desabilitado em testes
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'

# Cache em memória
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Evita erros de configuração de Channels, WhatsApp, etc.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

WHATSAPP_ACCESS_TOKEN = 'test-token'
WHATSAPP_VERIFY_TOKEN = 'test-verify'
ENCRYPTION_KEY = ''
