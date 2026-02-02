"""
Django base settings for WhatsApp Business Platform.
"""
import os
from pathlib import Path
from datetime import timedelta
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY', 'your-secret-key-change-in-production'))

DEBUG = os.environ.get('DEBUG', os.environ.get('DJANGO_DEBUG', 'False')).lower() == 'true'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')
# Add Railway domain automatically
ALLOWED_HOSTS.extend([
    'server-production-1e57.up.railway.app',
    '.up.railway.app',
    'healthcheck.railway.app',
])

INSTALLED_APPS = [
    'daphne',
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
    'storages',
    # Local apps
    'apps.core',
    'apps.whatsapp.apps.WhatsAppConfig',
    'apps.conversations',
    'apps.langflow',
    'apps.notifications',
    'apps.audit',
    'apps.campaigns',
    'apps.automation',
    'apps.stores',  # Multi-store management (unified)
    'apps.marketing',  # Email marketing with Resend
    'apps.instagram',  # Instagram Messaging API integration
    'apps.messaging',  # Unified messaging dispatcher
    'apps.webhooks',  # Centralized webhook handling
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
    'apps.core.middleware.TenantMiddleware',
    'apps.core.middleware.RequestLoggingMiddleware',
    'apps.core.middleware.RateLimitMiddleware',
]

ROOT_URLCONF = 'config.urls'

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

# Redis (shared)
REDIS_URL = os.environ.get('REDIS_URL', '').strip()

# Channels - use Redis if available, otherwise use in-memory
if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL:
    parsed_db = urlparse(DATABASE_URL)
    if parsed_db.scheme in ('postgres', 'postgresql'):
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': parsed_db.path.lstrip('/'),
                'USER': unquote(parsed_db.username or ''),
                'PASSWORD': unquote(parsed_db.password or ''),
                'HOST': parsed_db.hostname or 'localhost',
                'PORT': str(parsed_db.port or 5432),
            }
        }
        db_query = parse_qs(parsed_db.query)
        sslmode = db_query.get('sslmode', [None])[0]
        if sslmode:
            DATABASES['default']['OPTIONS'] = {'sslmode': sslmode}
    else:
        # Fallback to SQLite if DATABASE_URL is not PostgreSQL
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    # No DATABASE_URL - use SQLite as fallback
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

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
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000/minute',
        'user': '10000/minute',
        'webhook': '10000/hour',
    },
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

# CORS
# Note: CORS_ALLOW_ALL_ORIGINS cannot be True when CORS_ALLOW_CREDENTIALS is True
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:12001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:12001",
    "https://www.pastita.com.br",
    "https://pastita.com.br",
    "https://painel.pastita.com.br",
    "https://work-1-gvluusmmjgqnmmmw.prod-runtime.all-hands.dev",
    "https://work-2-gvluusmmjgqnmmmw.prod-runtime.all-hands.dev",
    "https://work-1-zdllsooldjqqzgtd.prod-runtime.all-hands.dev",
    "https://work-2-zdllsooldjqqzgtd.prod-runtime.all-hands.dev",
]
cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if cors_origins:
    CORS_ALLOWED_ORIGINS.extend([o.strip() for o in cors_origins.split(',') if o.strip()])

# Additional CORS settings
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-tenant-slug',
    'x-store-slug',
]
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CORS_EXPOSE_HEADERS = [
    'content-type',
    'x-csrftoken',
]

# Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL or 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL or 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Cache configuration - use Redis if available, otherwise use local memory
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# WhatsApp Business API
WHATSAPP_API_VERSION = os.environ.get('WHATSAPP_API_VERSION', 'v18.0')
WHATSAPP_API_BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN', 'your-verify-token')
WHATSAPP_APP_SECRET = os.environ.get('WHATSAPP_APP_SECRET', '')

# Default WhatsApp account configuration (existing account lookup + optional auto-create)
DEFAULT_WHATSAPP_ACCOUNT_NAME = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_NAME', 'Pastita WhatsApp Business')
DEFAULT_WHATSAPP_ACCOUNT_ID = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_ID', os.environ.get('ECOMMERCE_DEFAULT_ACCOUNT_ID', '')
).strip()
DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER', os.environ.get('PASTITA_WHATSAPP_NUMBER', '')
).strip()
DEFAULT_WHATSAPP_ACCOUNT_DISPLAY_NUMBER = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_DISPLAY_NUMBER', DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER
).strip()
DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER_ID = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER_ID', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_WABA_ID = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_WABA_ID', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_ACCESS_TOKEN = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_ACCESS_TOKEN', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_OWNER_EMAIL = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_OWNER_EMAIL', os.environ.get('ADMIN_EMAIL', '')
).strip()
DEFAULT_WHATSAPP_ACCOUNT_STATUS = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_STATUS', 'active').strip().lower()
DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE', 'False'
).strip().lower() == 'true'
_DEFAULT_WHATSAPP_STORE_SLUGS = os.environ.get('DEFAULT_WHATSAPP_STORE_SLUGS', '')
DEFAULT_WHATSAPP_STORE_SLUGS = [
    slug.strip() for slug in _DEFAULT_WHATSAPP_STORE_SLUGS.split(',') if slug.strip()
]
DEFAULT_WHATSAPP_STORE_METADATA_KEY = os.environ.get('DEFAULT_WHATSAPP_STORE_METADATA_KEY', 'whatsapp_account_id')

# Instagram API Configuration
INSTAGRAM_APP_ID = os.environ.get('INSTAGRAM_APP_ID', '955411496814093')
INSTAGRAM_APP_SECRET = os.environ.get('INSTAGRAM_APP_SECRET', '')
INSTAGRAM_WEBHOOK_VERIFY_TOKEN = os.environ.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN', 'pastita-ig-verify')

# Maps (HERE)
HERE_API_KEY = os.environ.get('HERE_API_KEY', '').strip()

# Base URL for webhooks and callbacks
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:12000')
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://web-production-3e83a.up.railway.app')
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'https://painel.pastita.com.br')

# Mercado Pago Integration
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get('MERCADO_PAGO_ACCESS_TOKEN', '')
MERCADO_PAGO_PUBLIC_KEY = os.environ.get('MERCADO_PAGO_PUBLIC_KEY', '')
PASTITA_WHATSAPP_NUMBER = os.environ.get('PASTITA_WHATSAPP_NUMBER', '5563992957931')
PASTITA_BASE_URL = os.environ.get('PASTITA_BASE_URL', 'https://agriao.shop')

# Meta Pixel (Conversions API)
META_PIXEL_ID = os.environ.get('META_PIXEL_ID', '').strip()
META_CAPI_ACCESS_TOKEN = os.environ.get('META_CAPI_ACCESS_TOKEN', '').strip()
META_CAPI_TEST_EVENT_CODE = os.environ.get('META_CAPI_TEST_EVENT_CODE', '').strip()
META_CAPI_VERSION = os.environ.get('META_CAPI_VERSION', 'v20.0').strip()

# Langflow
LANGFLOW_API_URL = os.environ.get('LANGFLOW_API_URL', 'http://localhost:7860')
LANGFLOW_API_KEY = os.environ.get('LANGFLOW_API_KEY', '')

# Rate Limiting
RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'True').lower() == 'true'
RATE_LIMIT_REQUESTS = int(os.environ.get('RATE_LIMIT_REQUESTS', '100'))
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', '60'))
_RATE_LIMIT_WHITELIST = os.environ.get('RATE_LIMIT_WHITELIST_PATHS', '/api/v1/stores/orders/by-token/,/api/v1/stores/stores/,/api/v1/notifications/')
RATE_LIMIT_WHITELIST_PATHS = [
    path.strip() for path in _RATE_LIMIT_WHITELIST.split(',') if path.strip()
]

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            '()': 'apps.core.logging.JsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'app.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# DRF Spectacular (OpenAPI)
SPECTACULAR_SETTINGS = {
    'TITLE': 'WhatsApp Business Platform API',
    'DESCRIPTION': 'API completa para integração com WhatsApp Business',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get('MERCADO_PAGO_ACCESS_TOKEN', '')
MERCADO_PAGO_WEBHOOK_SECRET = os.environ.get('MERCADO_PAGO_WEBHOOK_SECRET', '')
MERCADO_PAGO_STATEMENT_DESCRIPTOR = os.environ.get('MERCADO_PAGO_STATEMENT_DESCRIPTOR', 'PASTITA')
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://localhost:8000')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
ECOMMERCE_DEFAULT_ACCOUNT_ID = os.environ.get('ECOMMERCE_DEFAULT_ACCOUNT_ID', '').strip()

# AWS S3 Storage (optional)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'sa-east-1')

USE_S3 = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME)

MEDIA_ROOT = BASE_DIR / 'media'

if USE_S3:
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_DEFAULT_ACL = None
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
else:
    MEDIA_URL = '/media/'
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
