#!/bin/bash
# Backup PostgreSQL database com timestamp
# Uso: ./backup_database.sh

set -e

BACKUP_DIR="/app/backups"
DB_CONTAINER="pastita_db"
DB_NAME="pastita"
DB_USER="postgres"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/pastita_backup_$TIMESTAMP.sql.gz"
RETENTION_DAYS=30

# Criar diretório se não existir
mkdir -p "$BACKUP_DIR"

echo "🔄 Iniciando backup do banco de dados ($DB_NAME)..."

# Rodar pg_dump do container
docker compose exec -T "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ Backup criado: $BACKUP_FILE ($SIZE)"

    # Limpar backups antigos (> 30 dias)
    echo "🧹 Removendo backups com mais de $RETENTION_DAYS dias..."
    find "$BACKUP_DIR" -name "pastita_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete

    echo "✅ Backup finalizado com sucesso!"
else
    echo "❌ Erro ao fazer backup do banco de dados"
    exit 1
fi
