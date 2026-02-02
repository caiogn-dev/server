#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================

set -e

# Generate missing migrations automatically
python manage.py makemigrations --no-input automation messaging stores webhooks 2>/dev/null || true

# Run migrations
python manage.py migrate --noinput

# Execute command
exec "$@"
