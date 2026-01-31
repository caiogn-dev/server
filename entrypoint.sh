#!/bin/bash
# Production entrypoint for Railway deployment

set -e

PORT="${PORT:-8080}"

echo "=== Applying database migrations ==="
python manage.py migrate --noinput

echo "=== Setting up Pastita store ==="
python manage.py setup_pastita_store || echo "WARNING: setup_pastita_store had issues, but continuing..."

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Starting daphne (ASGI) on port ${PORT} ==="

exec python -m daphne \
    -b 0.0.0.0 \
    -p "${PORT}" \
    --proxy-headers \
    --access-log - \
    config.asgi:application
