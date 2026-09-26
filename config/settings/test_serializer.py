"""Settings minimalistas para testes de serializers (sem langchain/celery/channels)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = 'test-secret-key-not-for-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

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
    'apps.core',
    'apps.stores',
    'apps.users',
    'apps.conversations',
    'apps.whatsapp.apps.WhatsAppConfig',
    'apps.notifications',
    'apps.audit',
    'apps.campaigns',
    'apps.handover',
    'apps.messaging',
    'apps.webhooks',
    'apps.instagram',
    'apps.marketing',
    'apps.public_api',
    'apps.postado',
    'apps.orders',
    'apps.automation',
    'apps.agents',
    'apps.fiscal',
    'apps.mobile_api',
    'django_celery_beat',
]

SILENCED_SYSTEM_CHECKS = []

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'config.urls_minimal'

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

import tempfile as _tempfile  # noqa: E402
MEDIA_ROOT = _tempfile.mkdtemp(prefix='django_test_media_')

# `agents.0009` e `whatsapp.0007` usam AddIndexConcurrently (postgres-only);
# o schema editor do SQLite não aceita `concurrently=True`.  O patch abaixo
# faz a operação cair silenciosamente para AddIndex normal em backends que não
# sejam PostgreSQL, sem alterar as migrations em si nem quebrar dependências.
def _patch_add_index_concurrently():
    from django.contrib.postgres import operations as _pg_ops

    _orig_fwd = _pg_ops.AddIndexConcurrently.database_forwards
    _orig_bwd = _pg_ops.AddIndexConcurrently.database_backwards

    def _safe_forward(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != 'postgresql':
            model = to_state.apps.get_model(app_label, self.model_name)
            schema_editor.add_index(model, self.index)
        else:
            _orig_fwd(self, app_label, schema_editor, from_state, to_state)

    def _safe_backward(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != 'postgresql':
            model = from_state.apps.get_model(app_label, self.model_name)
            schema_editor.remove_index(model, self.index)
        else:
            _orig_bwd(self, app_label, schema_editor, from_state, to_state)

    _pg_ops.AddIndexConcurrently.database_forwards = _safe_forward
    _pg_ops.AddIndexConcurrently.database_backwards = _safe_backward


_patch_add_index_concurrently()

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# As TAXAS vêm de `base.py`, não de uma cópia.
#
# Este arquivo declarava a lista de escopos à mão e ela divergiu DUAS VEZES em
# uma semana: `auth` (PR #373) e `public_read`/`lead_create` (PR #375). O
# estrago não é um teste que falha e sim COMO ele falha — o DRF resolve a taxa
# dentro do `__init__` do throttle, antes de qualquer linha da view, e levanta
# `ImproperlyConfigured`. Os testes que quebraram foram justamente os de
# info-disclosure do OTP: enquanto estouravam na criação do throttle, nenhuma
# regressão de segurança nesses endpoints seria vista.
#
# Escopo novo em base.py passa a chegar aqui sozinho.
from .base import REST_FRAMEWORK as _REST_FRAMEWORK_BASE  # noqa: E402

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': dict(_REST_FRAMEWORK_BASE['DEFAULT_THROTTLE_RATES']),
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Sem Celery/Redis/Channels para estes testes
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'

# Cripto para tokens de automação
ENCRYPTION_KEY = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='

# Meta Graph API — necessário porque instagram_api.py lê em corpo de classe.
# Vem de base.py pelo mesmo motivo das taxas: a versão sobe e a cópia fica.
from .base import META_GRAPH_VERSION, META_GRAPH_URL  # noqa: E402,F401

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null']},
}
