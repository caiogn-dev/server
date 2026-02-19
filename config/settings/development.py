"""
Django development settings.
"""
from .base import *

DEBUG = True

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

CORS_ALLOW_ALL_ORIGINS = True

import os

# Ensure logs directory exists
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING['handlers']['file']['filename'] = BASE_DIR / 'logs' / 'dev.log'
