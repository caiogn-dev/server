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

# ── O Redis CRU também, não só o cache do Django ──────────────────────────
#
# A correção de 07/ago isolou CACHES e CHANNEL_LAYERS, mas deixou `REDIS_URL`
# apontando para `redis://redis:6379/1` — a loja viva. Quem chama
# `redis.from_url(settings.REDIS_URL)` direto (create_redis_client, memória do
# agente, acquire_lock) continuava indo no Redis de produção.
#
# Na rede de teste esse host nem resolve, então o sintoma era pior que um
# vazamento: `socket.gaierror -3` derrubando testes que nada tinham a ver com
# Redis, e parecendo falha de infraestrutura sem conserto.
#
# 🔑 O valor chega aqui pelo AMBIENTE DA IMAGEM: `docker commit` de um container
# em execução leva as variáveis dele junto, então a imagem de teste carrega o
# .env de produção. Não adianta "não passar --env-file".
#
# localhost de propósito: conexão recusada na hora, em vez de DNS pendurado.
REDIS_URL = 'redis://localhost:6379/0'
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# ⚠️ Sem este `pop`, as duas linhas acima são decorativas.
#
# Em Celery 5, `app.conf.broker_url` é uma *property* que consulta
# `os.environ['CELERY_BROKER_URL']` A CADA LEITURA, antes de olhar o settings.
# Ou seja: o ambiente do processo passa por cima do Django, e escrever
# `app.conf.broker_url = ...` não vence — a property lê o env de novo.
#
# E o ambiente aqui é o de PRODUÇÃO: `pastita_backend:latest` nasce de
# `docker commit pastita_web`, então carrega o env da loja viva assado dentro
# da imagem. Medido em 14/ago: a suíte tentava alcançar `redis://redis:6379`,
# levava 20 retries de 1s e queimava 129s POR TESTE antes de falhar. Parecia
# problema de ambiente sem conserto.
#
# Corrigir passando `-e` no runner seria tapa-buraco: protegeria só quem
# lembrasse de usar o runner. Removendo a variável, a property cai no settings
# e a regra vale para qualquer invocação — pytest, manage.py, CI, qualquer uma.
#
# É seguro apagar aqui: `base.py` já foi importado acima e já leu o env para
# dentro do settings. Produção não passa por este arquivo.
for _var in ('CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND', 'REDIS_URL'):
    os.environ.pop(_var, None)

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
