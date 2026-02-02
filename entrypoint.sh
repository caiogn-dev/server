#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================

set -e

# Generate and apply migrations in one go
python manage.py makemigrations --no-input automation messaging stores webhooks 2>/dev/null | head -20 && \
python manage.py migrate --noinput

# Execute command
exec "$@"
