#!/bin/sh
# Entrypoint script that runs migrations, seed (if needed), and starts Gunicorn

set -e

echo "🚀 Iniciando aplicação..."

# Run migrations
echo "📊 Executando migrações..."
python manage.py migrate

# Run collectstatic
echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

# Healthcheck: validate database integrity and auto-seed if needed
echo "🔍 Verificando integridade do banco de dados..."
python manage.py db_healthcheck --auto-seed || {
    echo "⚠️  Integridade do banco falhou, tentando seed automático..."
    python manage.py populate_ce_saladas_menu --force
    python manage.py populate_pastita_menu --force
    python manage.py populate_kero_kero_menu --force
    python manage.py populate_delivery_zones
    echo "✅ Seed automático completado"
}

# Start Gunicorn
echo "✅ Iniciando servidor..."
exec gunicorn config.asgi:application \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
