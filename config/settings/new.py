"""
Django settings - NOVO SISTEMA (apenas apps v2).
"""
import os
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = ['*']

# APENAS APPS NOVOS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',
    'django_celery_beat',
    # Apps novos
    'apps.core_v2.apps.CoreV2Config',
    'apps.commerce.apps.CommerceConfig',
    'apps.messaging_v2.apps.MessagingV2Config',
    'apps.marketing_v2.apps.MarketingV2Config',
]

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

ROOT_URLCONF = 'config.urls_new'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://postgres:postgres123@localhost:5432/pastita')
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': unquote(parsed.username or ''),
            'PASSWORD': unquote(parsed.password or ''),
            'HOST': parsed.hostname or 'localhost',
            'PORT': str(parsed.port or 5432),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Redis
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# CORS - usar variáveis de ambiente apenas
_cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _cors_origins:
    CORS_ORIGIN_WHITELIST = [url.strip() for url in _cors_origins.split(',') if url.strip()]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'content-type',
    'authorization',
    'x-csrftoken',
    'x-requested-with',
    'accept',
    'origin',
    'user-agent',
]

# CSRF - usar variáveis de ambiente apenas
_csrf_env = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS') or os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [url.strip() for url in _csrf_env.split(',') if url.strip()]

# Cookies
_csrf_secure = os.environ.get('CSRF_COOKIE_SECURE', '').lower() == 'true'
CSRF_COOKIE_SECURE = _csrf_secure
SESSION_COOKIE_SECURE = _csrf_secure
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

# Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'Pastita API',
    'DESCRIPTION': 'API do sistema Pastita',
    'VERSION': '2.0.0',
}

# Celery Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'America/Sao_Paulo'
CELERY_ENABLE_UTC = True

# Performance settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_RESULT_EXPIRES = 3600

# Beat scheduler
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Webhook secrets (from environment)
WHATSAPP_VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'pastita-webhook-token')
WHATSAPP_APP_SECRET = os.environ.get('WHATSAPP_APP_SECRET', '')
INSTAGRAM_VERIFY_TOKEN = os.environ.get('INSTAGRAM_VERIFY_TOKEN', 'pastita-instagram-token')
