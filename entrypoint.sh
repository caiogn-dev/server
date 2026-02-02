#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - MAIN ENTRYPOINT
# ============================================================================
# Handles database migrations, health checks, and startup
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[ENTRYPOINT]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[ENTRYPOINT]${NC} WARNING: $1"
}

error() {
    echo -e "${RED}[ENTRYPOINT]${NC} ERROR: $1"
}

# Wait for database to be ready
wait_for_db() {
    log "Waiting for database..."
    
    if [ -z "$DATABASE_URL" ]; then
        warn "DATABASE_URL not set, skipping database check"
        return 0
    fi
    
    # Extract host from DATABASE_URL (postgresql://user:pass@host:port/db)
    DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\).*/\1/p')
    
    if [ -z "$DB_HOST" ]; then
        warn "Could not parse DATABASE_URL, skipping database check"
        return 0
    fi
    
    log "Checking connection to $DB_HOST..."
    
    for i in {1..30}; do
        if nc -z "$DB_HOST" 5432 2>/dev/null; then
            log "Database is ready!"
            return 0
        fi
        log "Attempt $i/30: Database not ready yet, waiting..."
        sleep 2
    done
    
    error "Database connection timeout after 60 seconds"
    return 1
}

# Wait for Redis to be ready
wait_for_redis() {
    log "Waiting for Redis..."
    
    if [ -z "$REDIS_URL" ]; then
        warn "REDIS_URL not set, skipping Redis check"
        return 0
    fi
    
    # Extract host from REDIS_URL (redis://host:port/db)
    REDIS_HOST=$(echo $REDIS_URL | sed -n 's/.*:\/\/\([^:]*\).*/\1/p')
    
    if [ -z "$REDIS_HOST" ]; then
        warn "Could not parse REDIS_URL, skipping Redis check"
        return 0
    fi
    
    log "Checking connection to Redis at $REDIS_HOST..."
    
    for i in {1..30}; do
        if nc -z "$REDIS_HOST" 6379 2>/dev/null; then
            log "Redis is ready!"
            return 0
        fi
        log "Attempt $i/30: Redis not ready yet, waiting..."
        sleep 2
    done
    
    error "Redis connection timeout after 60 seconds"
    return 1
}

# Run database migrations
run_migrations() {
    log "Running database migrations..."
    python manage.py migrate --noinput
    log "Migrations complete!"
}

# Create cache tables (for database cache backend)
setup_cache() {
    if [ "$CACHE_BACKEND" = "django.core.cache.backends.db.DatabaseCache" ]; then
        log "Setting up database cache..."
        python manage.py createcachetable || true
    fi
}

# Check if running on Railway (production)
is_railway() {
    [ -n "$RAILWAY_ENVIRONMENT" ]
}

# Main startup sequence
main() {
    log "Starting Pastita Platform..."
    log "Environment: ${RAILWAY_ENVIRONMENT:-development}"
    
    # Wait for dependencies
    wait_for_db || exit 1
    wait_for_redis || exit 1
    
    # Run setup tasks (only for web container)
    if [ -z "$SKIP_MIGRATIONS" ]; then
        run_migrations
        setup_cache
    fi
    
    # Health check endpoint
    log "Application ready!"
    log "Command: $@"
    
    exec "$@"
}

# Run main function
main "$@"
