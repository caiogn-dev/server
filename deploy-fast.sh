#!/usr/bin/env bash
# Deploy RÁPIDO do server2 via docker cp (segundos, sem rebuild de imagem).
#
# A imagem (Dockerfile.prod) NÃO monta o código-fonte — editar arquivo local
# não muda nada em produção. Este script sincroniza apps/ e config/ inteiros
# para dentro do container (deleções locais também são aplicadas) e reinicia.
#
# Para deploy definitivo (deps novas, Dockerfile, etc) use ./deploy.sh (rebuild).
#
# Uso:
#   ./deploy-fast.sh             # sincroniza código + restart
#   ./deploy-fast.sh --migrate   # idem, rodando migrações antes do restart
set -euo pipefail
cd "$(dirname "$0")"

CONTAINER=pastita_web

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "ERRO: container $CONTAINER não existe." >&2
  exit 1
fi

echo "==> Validando sintaxe Python local..."
find apps config -name '*.py' -not -path '*/migrations/*' -print0 | xargs -0 python3 -m py_compile

echo "==> Sincronizando apps/ e config/ para $CONTAINER:/app/ ..."
docker exec "$CONTAINER" rm -rf /app/apps.new /app/config.new
docker cp apps "$CONTAINER":/app/apps.new
docker cp config "$CONTAINER":/app/config.new
docker exec "$CONTAINER" sh -c 'rm -rf /app/apps /app/config && mv /app/apps.new /app/apps && mv /app/config.new /app/config'

if [[ "${1:-}" == "--migrate" ]]; then
  echo "==> Rodando migrações..."
  docker exec "$CONTAINER" python manage.py migrate
fi

echo "==> Reiniciando $CONTAINER..."
docker restart "$CONTAINER" >/dev/null

echo -n "==> Aguardando health"
for _ in $(seq 1 30); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo none)
  if [[ "$status" == "healthy" ]]; then break; fi
  echo -n "."
  sleep 2
done
echo " $status"

code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/v1/stores/pastita/ || true)
echo "==> Smoke test GET /api/v1/stores/pastita/ -> $code"
if [[ "$status" != "healthy" || "$code" != "200" ]]; then
  echo "ERRO: deploy suspeito — confira: docker logs $CONTAINER --tail 50" >&2
  exit 1
fi
echo "==> Deploy OK"
