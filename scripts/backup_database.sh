#!/bin/bash
# Backup do PostgreSQL no DISCO DO HOST (não no container), com verificação de
# integridade e rotação. Agendar via cron (ver instruções no fim do arquivo).
#
# Uso: ./scripts/backup_database.sh

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────
BACKUP_DIR="${PASTITA_BACKUP_DIR:-/home/graco/backups/pastita}"   # caminho no HOST
DB_CONTAINER="pastita_db"
DB_NAME="pastita"
DB_USER="postgres"
RETENTION_DAYS="${PASTITA_BACKUP_RETENTION_DAYS:-30}"
# Offsite opcional: defina PASTITA_BACKUP_OFFSITE_CMD para enviar para fora da
# máquina (ex.: 'rclone copy {file} b2:meu-bucket/pastita'). {file} é substituído.
OFFSITE_CMD="${PASTITA_BACKUP_OFFSITE_CMD:-}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/pastita_backup_$TIMESTAMP.sql.gz"
LOG_FILE="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "🔄 Iniciando backup de '$DB_NAME' → $BACKUP_FILE"

# Dump direto do container (container name; não precisa de docker compose context)
if ! docker exec -t "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    log "❌ pg_dump falhou"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Verificação de integridade: gzip íntegro e dump não-vazio
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    log "❌ Backup corrompido (gzip inválido) — removendo"
    rm -f "$BACKUP_FILE"
    exit 1
fi
SIZE_BYTES=$(stat -c%s "$BACKUP_FILE")
if [ "$SIZE_BYTES" -lt 10000 ]; then
    log "❌ Backup suspeito (apenas ${SIZE_BYTES} bytes) — removendo"
    rm -f "$BACKUP_FILE"
    exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "✅ Backup OK: $SIZE"

# Offsite opcional (proteção contra falha de disco)
if [ -n "$OFFSITE_CMD" ]; then
    CMD="${OFFSITE_CMD//\{file\}/$BACKUP_FILE}"
    log "☁️  Enviando offsite: $CMD"
    if eval "$CMD"; then log "✅ Offsite OK"; else log "⚠️  Offsite FALHOU (backup local preservado)"; fi
fi

# Rotação
DELETED=$(find "$BACKUP_DIR" -name "pastita_backup_*.sql.gz" -mtime "+$RETENTION_DAYS" -print -delete | wc -l)
log "🧹 Rotação: removidos $DELETED backup(s) > ${RETENTION_DAYS} dias. Total atual: $(find "$BACKUP_DIR" -name 'pastita_backup_*.sql.gz' | wc -l)"
log "✅ Concluído."

# ── Agendar (rodar uma vez na mão) ──────────────────────────────────────
#   (crontab -l 2>/dev/null; echo "0 3 * * * /home/graco/WORK/server2/scripts/backup_database.sh >> /home/graco/backups/pastita/cron.log 2>&1") | crontab -
#
# ── Restaurar um backup ─────────────────────────────────────────────────
#   gunzip -c /home/graco/backups/pastita/pastita_backup_AAAAMMDD_HHMMSS.sql.gz | docker exec -i pastita_db psql -U postgres -d pastita
