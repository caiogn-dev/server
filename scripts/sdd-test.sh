#!/bin/bash
# SDD test helper: sincroniza o source do host (container é baked, sem volume)
# para dentro de pastita_web e roda pytest com os args passados.
# Uso: bash scripts/sdd-test.sh apps/core/tests/test_no_bom.py -v
#
# IMPORTANTE — banco de testes x pgbouncer:
# A app conecta no Postgres via pgbouncer (transaction pooling). O pgbouncer
# está fixado no database `pastita`, então o `CREATE DATABASE test_pastita`
# do test runner é criado mas TODAS as queries do teste acabam roteadas para
# o banco `pastita` de produção (current_database() = pastita). Resultado:
# os testes liam/escreviam dados reais e quebravam por UniqueViolation
# (ex.: custom_domain 'cesaladas.com.br' já existe). A correção é apontar o
# DATABASE_URL dos testes direto para o Postgres (pastita_db:5432), sem passar
# pelo pgbouncer, para que o test_pastita isolado seja realmente usado.
set -e
docker cp pytest.ini pastita_web:/app/pytest.ini >/dev/null
docker cp apps/. pastita_web:/app/apps/ >/dev/null

# Reescreve o host/porta do pgbouncer para o Postgres direto, preservando
# usuário/senha/credenciais do DATABASE_URL existente (sem hardcode de segredo).
TEST_DATABASE_URL="$(docker compose exec -T web python - <<'PY'
import os
url = os.environ.get('DATABASE_URL', '')
url = url.replace('pastita_pgbouncer:6432', 'pastita_db:5432')
url = url.replace('@pgbouncer:6432', '@pastita_db:5432')
print(url)
PY
)"
TEST_DATABASE_URL="$(printf '%s' "$TEST_DATABASE_URL" | tr -d '\r\n')"

docker compose exec -T -e DATABASE_URL="$TEST_DATABASE_URL" web python -m pytest "$@"
