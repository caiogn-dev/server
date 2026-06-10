#!/bin/bash
# Deploy seguro do server2 (Docker Compose, nginx :8001)
# - NÃO faz git add/commit/push (deploy é deploy, commit é commit)
# - NÃO faz `compose down` (evita derrubar db/redis junto)
# - Rebuilda e recria só os serviços de app, roda migrate, healthcheck no final
set -euo pipefail

cd "$(dirname "$0")"

echo "[deploy] commit atual: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "[deploy] AVISO: working tree sujo — você está deployando código não commitado." >&2
fi

echo "[deploy] build da imagem..."
docker compose build web

echo "[deploy] recriando serviços de app (db/redis ficam no ar)..."
docker compose up -d --no-deps web celery celery-beat

echo "[deploy] migrations..."
docker compose exec -T web python manage.py migrate --noinput

echo "[deploy] collectstatic..."
docker compose exec -T web python manage.py collectstatic --noinput >/dev/null 2>&1 || true

echo "[deploy] healthcheck..."
for i in $(seq 1 20); do
  sleep 3
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8001/api/sse/health/ || true)"
  if [[ "$code" == "200" ]]; then
    echo "[deploy] OK (HTTP 200) — deploy concluído."
    docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'pastita_(web|celery|celery_beat|nginx)'
    exit 0
  fi
  echo "[deploy] aguardando API (tentativa $i/20, HTTP ${code:-000})..."
done

echo "[deploy] FALHA: API não respondeu 200. Logs recentes:" >&2
docker logs pastita_web --tail 50 >&2
exit 1
