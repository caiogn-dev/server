#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================

set -e

# Apply migrations
python manage.py migrate --noinput

# Start the application
exec "$@"
