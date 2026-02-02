#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================

set -e

# Run migrations (skip if fails)
python manage.py migrate --noinput || true

# Start the application
exec "$@"
