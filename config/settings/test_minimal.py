"""Configurações mínimas para testes unitários sem banco/redis."""
SECRET_KEY = 'test-secret-key-apenas-para-testes'
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'rest_framework',
    'apps.core',
    'apps.whatsapp',
    'apps.stores',
    'apps.agents',
    'apps.users',
    'apps.automation',
    'apps.conversations',
]
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
SILENCED_SYSTEM_CHECKS = ['*']
AUTH_USER_MODEL = 'auth.User'
