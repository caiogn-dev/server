#!/bin/bash
set -e

echo "=== Starting Application ==="
echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating admin user..."
python manage.py create_admin || echo "Admin already exists"

echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 --log-level info
