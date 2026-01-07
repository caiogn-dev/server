"""
Django settings for server project.
Production-ready configuration with security best practices.
"""

from pathlib import Path
from decouple import config
from dotenv import load_dotenv
import os
import sys
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root (works regardless of current working dir)
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

# Allowed hosts - specific hosts for security
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'web-production-3e83a.up.railway.app',
    'pastita.com.br',
    'www.pastita.com.br',
]

# Add Railway and other dynamic hosts
if os.environ.get('RAILWAY_STATIC_URL'):
    ALLOWED_HOSTS.append(os.environ.get('RAILWAY_STATIC_URL').replace('https://', '').replace('http://', ''))

# Allow all hosts in debug mode for development convenience
if DEBUG:
    ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'corsheaders',            # Tem que estar aqui
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'api',
    'storages',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',         # OBRIGATÓRIO SER O PRIMEIRO
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',    # ADICIONADO: Essencial para produção
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'server.urls'

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

WSGI_APPLICATION = 'server.wsgi.application'
ASGI_APPLICATION = 'server.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# Database
# Configuração híbrida: usa DATABASE_URL quando disponível, senão SQLite local.
DATABASE_URL = config('DATABASE_URL', default='')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
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

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Compressão do WhiteNoise para performance
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'api.User'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.authentication.CookieTokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    },
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://pastita.com.br",
    "https://www.pastita.com.br",
    "https://web-production-3e83a.up.railway.app",
]

# Add dynamic frontend URL from environment
FRONTEND_CORS = config('FRONTEND_URL', default='')
if FRONTEND_CORS and FRONTEND_CORS not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append(FRONTEND_CORS)

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "https://pastita.com.br",
    "https://www.pastita.com.br",
    "https://web-production-3e83a.up.railway.app",
]

# Add dynamic frontend URL to CSRF trusted origins
if FRONTEND_CORS and FRONTEND_CORS not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(FRONTEND_CORS)

# CSRF Cookie settings for SPA
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript to read the cookie
CSRF_COOKIE_SAMESITE = 'Lax' if DEBUG else 'None'
SESSION_COOKIE_SAMESITE = 'Lax' if DEBUG else 'None'
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'

# In production, use secure cookies
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

CORS_ALLOW_CREDENTIALS = True
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
]

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = config('MERCADO_PAGO_ACCESS_TOKEN', default='')
MERCADO_PAGO_WEBHOOK_SECRET = config('MERCADO_PAGO_WEBHOOK_SECRET', default='')
BACKEND_URL = config('BACKEND_URL', default='http://localhost:8000')
FRONTEND_URL = config('FRONTEND_URL', default='https://pastita.com.br')

# Auth cookie (HttpOnly token)
AUTH_COOKIE_NAME = config('AUTH_COOKIE_NAME', default='auth_token')
AUTH_COOKIE_SECURE = config('AUTH_COOKIE_SECURE', default=not DEBUG, cast=bool)
AUTH_COOKIE_SAMESITE = config('AUTH_COOKIE_SAMESITE', default='None' if not DEBUG else 'Lax')
AUTH_COOKIE_DOMAIN = config('AUTH_COOKIE_DOMAIN', default='')

FRONTEND_IS_HTTPS = FRONTEND_URL.startswith('https://')
if FRONTEND_IS_HTTPS:
    CSRF_COOKIE_SAMESITE = 'None'
    SESSION_COOKIE_SAMESITE = 'None'
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    AUTH_COOKIE_SAMESITE = 'None'
    AUTH_COOKIE_SECURE = True

# --- CONFIGURACAO AWS S3 ---
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')

USE_S3 = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME)

if USE_S3:
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='sa-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_DEFAULT_ACL = None

    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
else:
    MEDIA_URL = '/media/'
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

MEDIA_ROOT = BASE_DIR / 'media'

# Mercado Pago additional settings
MERCADO_PAGO_STATEMENT_DESCRIPTOR = config('MERCADO_PAGO_STATEMENT_DESCRIPTOR', default='PASTITA')

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'api': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'api.mercado_pago': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True




