"""Settings minimalistas para testes de serializers (sem langchain/celery/channels)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = 'test-secret-key-not-for-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',
    'apps.core',
    'apps.stores',
    'apps.users',
    'apps.conversations',
    'apps.whatsapp.apps.WhatsAppConfig',
    'apps.notifications',
    'apps.audit',
    'apps.campaigns',
    'apps.handover',
    'apps.messaging',
    'apps.webhooks',
    'apps.instagram',
    'apps.marketing',
    'apps.public_api',
    'apps.postado',
    'apps.orders',
    'apps.automation',
    'apps.agents',
]

SILENCED_SYSTEM_CHECKS = []

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'config.urls_minimal'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/minute',
        'user': '1000/minute',
        'order_token': '30/minute',
        'public_write': '60/minute',
        'checkout': '30/minute',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Sem Celery/Redis/Channels para estes testes
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'

# Cripto para tokens de automação
ENCRYPTION_KEY = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null']},
}
