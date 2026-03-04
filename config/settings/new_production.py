"""
Django settings para produção com apps novos - SIMPLIFICADO.
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

# Remover middlewares problemáticos
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URLs simplificadas
ROOT_URLCONF = 'config.urls_migration'
