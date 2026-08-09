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

# ── Cache em memória, NUNCA o Redis compartilhado ─────────────────────────
#
# O banco foi isolado em 07/ago; o cache não. A suíte continuava usando
# `redis://redis:6379/1` — o mesmo Redis da loja viva — e isso causava dois
# estragos:
#
# 1. O contador de rate limit do DRF mora no cache e tem TTL de 1 hora. Cada
#    rodada da suíte deixava a cota consumida, então a rodada seguinte começava
#    saturada e ~43 testes (fidelidade, contratos do app, IDOR, LGPD) falhavam
#    com 429. Passavam isolados e falhavam na suíte inteira — o sintoma perfeito
#    para ser confundido com regressão, e foi.
#
# 2. Testes escreviam no cache de PRODUÇÃO: cardápio, sessões do bot, throttle
#    de clientes reais. A mesma classe de problema do banco, um andar acima.
#
# `locmem` nasce vazio a cada processo: a cota de throttle é sempre a mesma, e
# nada do teste sai do processo.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'testes',
    }
}

# Channels em memória pelo mesmo motivo: o layer padrão aponta para o Redis da
# produção e os testes de WebSocket passariam a disputar canais com a loja viva.
CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
}

# ── Cobrança DESLIGADA e credenciais falsas ───────────────────────────────
#
# O harness roda com `--env-file .env`, que é o de PRODUÇÃO: em 08/ago/2026 a
# suíte gerou SEIS cobranças PIX reais de R$ 179 na conta Mercado Pago da
# empresa. `test_active_untouched` cria a loja `s4` com trial vencido e chama
# `enforce_subscription_lifecycle()` sem mockar o SDK; com
# `BILLING_PIX_ENABLED=true` herdado do .env, a task foi até a API do MP.
#
# O rastro no extrato era `s4@cardapidex.com.br` — o padrão
# `{slug}@cardapidex.com.br` que o serviço usa quando a loja não tem email.
#
# Aqui as duas travas ficam desligadas por padrão. Teste que precisa do
# comportamento liga com `override_settings` E mocka o SDK.
BILLING_PIX_ENABLED = False
BILLING_ENFORCEMENT_ENABLED = False

# Credenciais obviamente inválidas: se algum caminho escapar dos mocks, ele
# falha na autenticação em vez de mexer na conta real.
MERCADOPAGO_ACCESS_TOKEN = 'TEST-TOKEN-FALSO-NAO-USAR'
MP_ACCESS_TOKEN = 'TEST-TOKEN-FALSO-NAO-USAR'

# Hash rápido: a suíte cria muitos usuários e o PBKDF2 domina o tempo.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
