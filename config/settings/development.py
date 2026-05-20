"""
Django development settings.
"""
import os

# Garante que SECRET_KEY tenha um valor padrão em desenvolvimento antes de importar base
if not os.environ.get('SECRET_KEY') and not os.environ.get('DJANGO_SECRET_KEY'):
    os.environ['SECRET_KEY'] = 'dev-only-insecure-secret-key-do-not-use-in-production'

from .base import *

DEBUG = True

# Keep DATABASE_URL support from base settings.
# Fallback to local SQLite only when DATABASE_URL is not provided.
if not os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Explicit local frontend allowlist for development (CORS + CSRF)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(CORS_ALLOWED_ORIGINS + [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:3010',
    'http://127.0.0.1:3010',
]))
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:3010',
    'http://127.0.0.1:3010',
]

# Ensure logs directory exists
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING['handlers']['file']['filename'] = BASE_DIR / 'logs' / 'dev.log'
