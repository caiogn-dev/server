#!/bin/bash
# ============================================================================
# PASTITA PLATFORM - CELERY ENTRYPOINT
# ============================================================================
# Specialized entrypoint for Celery workers and beat scheduler
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[CELERY]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[CELERY]${NC} WARNING: $1"
}

# Wait for Redis to be ready
wait_for_redis() {
    log "Waiting for Redis..."
    
    if [ -z "$CELERY_BROKER_URL" ]; then
        warn "CELERY_BROKER_URL not set, skipping Redis check"
        return 0
    fi
    
    # Extract host from CELERY_BROKER_URL (redis://host:port/db)
    REDIS_HOST=$(echo $CELERY_BROKER_URL | sed -n 's/.*:\/\/\([^:]*\).*/\1/p')
    
    if [ -z "$REDIS_HOST" ]; then
        warn "Could not parse CELERY_BROKER_URL, skipping Redis check"
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

# Wait for database to be ready (workers need DB access)
wait_for_db() {
    log "Waiting for database..."
    
    if [ -z "$DATABASE_URL" ]; then
        warn "DATABASE_URL not set, skipping database check"
        return 0
    fi
    
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

# Main startup
main() {
    log "Starting Celery..."
    log "Role: ${HOSTNAME:-worker}"
    
    # Wait for dependencies
    wait_for_redis || exit 1
    wait_for_db || exit 1
    
    log "Celery ready!"
    log "Command: $@"
    
    exec "$@"
}

main "$@"
