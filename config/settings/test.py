"""Settings da suíte de testes — banco SEPARADO de produção.

Existe porque não existia: até 07/ago/2026 o `pytest` deste repositório rodava
contra o banco `pastita`, o de produção. Não havia `TEST['NAME']` configurado e
o `DATABASE_URL` apontava para o pgbouncer da loja viva.

O que segurou o estrago foi o `TestCase` do Django, que envolve cada teste numa
transação e faz rollback. Mas essa proteção falha em dois casos, e os dois
aconteceram: `TransactionTestCase` commita de verdade, e execução interrompida
no meio deixa dado para trás. Prova: o usuário `ws-test` (id 6475) foi criado
por um teste em 05/ago e ficou no banco da loja.

Aqui o banco é o container `pastita_test_db`, que já existia e não estava sendo
usado. E não vai direto no Postgres — pgbouncer não suporta CREATE DATABASE, e
é dele que o pytest precisa para montar o `test_*`.

A trava de verdade está em `conftest.py`, na raiz: ela aborta a sessão se o
banco configurado for o de produção, independente de qual settings foi usado.
"""
import os

from .development import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('TEST_DB_NAME', 'test'),
        'USER': os.environ.get('TEST_DB_USER', 'test'),
        'PASSWORD': os.environ.get('TEST_DB_PASSWORD', 'test'),
        'HOST': os.environ.get('TEST_DB_HOST', 'pastita_test_db'),
        'PORT': os.environ.get('TEST_DB_PORT', '5432'),
        'CONN_MAX_AGE': 0,
        'TEST': {
            # Nome explícito: sem isto o Django deriva `test_<NAME>`, e um NAME
            # errado passaria despercebido.
            'NAME': 'test_pastita',
        },
    }
}

# Testes não devem depender de Redis/Celery reais.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Hash rápido: a suíte cria muitos usuários e o PBKDF2 domina o tempo.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
