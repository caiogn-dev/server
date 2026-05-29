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
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Reduce default 2-week session lifetime to 7 days.
SESSION_COOKIE_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

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

# Override base.py CORS list to exclude localhost / dev origins in production.
# Additional origins can be injected via CORS_ALLOWED_ORIGINS env var (comma-separated).
CORS_ALLOWED_ORIGINS = [
    "https://painel.pastita.com.br",
    "https://pastita.com.br",
    "https://www.pastita.com.br",
    "https://backend.pastita.com.br",
    "https://api.pastita.com.br",
]
_extra_cors = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _extra_cors:
    CORS_ALLOWED_ORIGINS.extend([o.strip() for o in _extra_cors.split(',') if o.strip()])

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
