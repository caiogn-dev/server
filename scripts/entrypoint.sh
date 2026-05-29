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

# Seed initial data if database is empty
echo "🌱 Verificando seed inicial..."
python manage.py initial_seed

# Healthcheck: validate database integrity
echo "🔍 Verificando integridade do banco de dados..."
python manage.py db_healthcheck

# Start Gunicorn
echo "✅ Iniciando servidor..."
exec gunicorn config.asgi:application \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
