"""
Django settings for migration - APENAS APPS NOVOS.
"""
from .base import *

# APENAS APPS NOVOS E ESSENCIAIS
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
    'drf_spectacular',
    'channels',
    'django_celery_beat',
    # APENAS APPS NOVOS
    'apps.core_v2.apps.CoreV2Config',
    'apps.commerce.apps.CommerceConfig',
    'apps.messaging_v2.apps.MessagingV2Config',
    'apps.marketing_v2.apps.MarketingV2Config',
]

# URLs simplificadas
ROOT_URLCONF = 'config.urls_migration'
