#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================

set -e

# Skip wait for db/redis - Railway handles this
# Run migrations
python manage.py migrate --noinput

# Execute command
exec "$@"
