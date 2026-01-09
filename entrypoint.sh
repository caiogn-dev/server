#!/usr/bin/env sh
set -e

echo "Starting Application Entrypoint Script"
echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating admin user..."
python manage.py create_admin || echo "Admin already exists"

PORT="${PORT:-8080}"
echo "=== Starting gunicorn on port ${PORT} ==="

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
