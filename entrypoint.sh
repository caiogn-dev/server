#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================

set -e

# Generate migrations for all apps that need it
python manage.py makemigrations --no-input automation messaging stores webhooks

# Apply all migrations
python manage.py migrate --noinput

# Start the application
exec "$@"
