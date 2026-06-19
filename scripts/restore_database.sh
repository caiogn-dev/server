#!/bin/bash
# Restore de disaster-recovery do Postgres a partir de um dump do backup_database.sh.
# Restaura e JÁ ressincroniza as sequences (resync_sequences.sh) — sem isso o
# banco entra em crash loop no próximo INSERT/migrate.
#
# Uso:
#   scripts/restore_database.sh [arquivo.sql.gz]
#   (sem argumento usa o backup mais recente em PASTITA_BACKUP_DIR)
#
# INTERATIVO de propósito (pede confirmação) — não usar em automação.
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-pastita_db}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-pastita}"
BACKUP_DIR="${PASTITA_BACKUP_DIR:-/home/graco/backups/pastita}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE="$(ls -t "$BACKUP_DIR"/pastita_backup_*.sql.gz 2>/dev/null | head -1 || true)"
fi
[ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ] || { echo "❌ Backup não encontrado: '${BACKUP_FILE:-vazio}'"; exit 1; }

echo "Backup:   $BACKUP_FILE"
echo "Destino:  ${DB_NAME}@${DB_CONTAINER}"
echo "Tamanho:  $(du -h "$BACKUP_FILE" | cut -f1)"

# Integridade antes de tocar no banco
gzip -t "$BACKUP_FILE" 2>/dev/null || { echo "❌ gzip corrompido — abortando"; exit 1; }

echo
echo "⚠️  Isto vai SOBRESCREVER o banco '${DB_NAME}'. Pare a app antes (docker stop pastita_web pastita_celery pastita_celery_beat)."
read -r -p "Digite SIM para continuar: " ok
[ "$ok" = "SIM" ] || { echo "Abortado."; exit 1; }

echo "[restore] aplicando dump..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"

echo "[restore] ressincronizando sequences..."
DB_CONTAINER="$DB_CONTAINER" DB_USER="$DB_USER" DB_NAME="$DB_NAME" bash "$SCRIPT_DIR/resync_sequences.sh"

echo "✅ Restore concluído. Suba a app de volta (docker start / docker compose up -d)."
