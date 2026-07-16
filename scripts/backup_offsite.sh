#!/bin/bash
# Envia um backup pro remoto rclone (offsite) e faz rotação remota.
# Chamado pelo backup_database.sh via PASTITA_BACKUP_OFFSITE_CMD (o {file}
# é substituído lá). Falha aqui NÃO derruba o backup local.
#
# Requisito único: remote autenticado — `rclone config reconnect gdrive:`
# (uma vez, abre o navegador). Teste: ./scripts/backup_offsite.sh <arquivo>
set -uo pipefail

FILE="${1:?uso: backup_offsite.sh <arquivo>}"
REMOTE="${PASTITA_BACKUP_REMOTE:-gdrive:backups/pastita}"
RETENTION_DAYS="${PASTITA_BACKUP_RETENTION_DAYS:-30}"

rclone copy "$FILE" "$REMOTE" --drive-use-trash=false || exit 1

# Rotação remota (mesma janela do local). Escopada ao padrão dos dumps para
# nunca apagar outra coisa que viva na pasta.
rclone delete "$REMOTE" --min-age "${RETENTION_DAYS}d" \
    --include 'pastita_backup_*.sql.gz' --drive-use-trash=false || true

echo "offsite ok: $(basename "$FILE") → $REMOTE"
