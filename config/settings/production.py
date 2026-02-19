"""
Django production settings.
"""
from .base import *
import os
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

# Add WhiteNoise middleware for serving static files
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# WhiteNoise configuration - override staticfiles storage
STORAGES["staticfiles"] = {
  "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
}
       
WHITENOISE_MANIFEST_STRICT = False
WHITENOISE_KEEP_ONLY_HASHED_FILES = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Disable SSL redirect - Cloudflare/Nginx handles HTTPS at the proxy level
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Trust headers from Cloudflare/Nginx
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Enforce required production settings
if SECRET_KEY == 'your-secret-key-change-in-production':
    raise ImproperlyConfigured('SECRET_KEY must be set in production.')

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must be set in production.')

# CORS - never allow all in production
CORS_ALLOW_ALL_ORIGINS = False

# ==============================================================================
# CSRF TRUSTED ORIGINS (FIX CRÍTICO)
# ==============================================================================
# Lê DJANGO_CSRF_TRUSTED_ORIGINS primeiro, fallback para CSRF_TRUSTED_ORIGINS
_csrf_env = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS') or os.environ.get('CSRF_TRUSTED_ORIGINS')

if _csrf_env:
    # Remove espaços em branco e cria a lista
    CSRF_TRUSTED_ORIGINS = [url.strip() for url in _csrf_env.split(',') if url.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'apps.core.logging.JsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
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
        'django.security.csrf': {
            'handlers': ['console'],
            'level': 'WARNING',  # Para ver os erros de 403 no log
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
