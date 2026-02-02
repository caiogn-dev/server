# ============================================================================
# PASTITA PLATFORM - MULTI-STAGE DOCKERFILE (Railway Optimized)
# ============================================================================
# Compatível com deploy atual no Railway
# 
# Targets:
#   production (default) - Django Web ASGI
#   celery     - Celery Worker
#   beat       - Celery Beat Scheduler
#   langflow-worker - Dedicated Langflow Queue Worker
#
# Railway usa automaticamente o target "production"
# ============================================================================

# ----------------------------------------------------------------------------
# STAGE 1: Base Python Image
# ----------------------------------------------------------------------------
FROM python:3.11-slim as python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Railway specific
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------
# STAGE 2: Builder (Install Python dependencies)
# ----------------------------------------------------------------------------
FROM python-base as builder

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------------
# STAGE 3: Production (Django Web - Default for Railway)
# ----------------------------------------------------------------------------
FROM python-base as production

ENV DJANGO_SETTINGS_MODULE=config.settings.production

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs staticfiles media

# Create non-root user (Railway best practice)
RUN addgroup --system appuser \
    && adduser --system --ingroup appuser appuser \
    && chown -R appuser:appuser /app

# Collect static files (with dummy values for build)
RUN DJANGO_ALLOWED_HOSTS=localhost \
    DJANGO_SECRET_KEY=build-time-secret-key-for-collectstatic-only \
    DATABASE_URL=sqlite:///tmp/db.sqlite3 \
    REDIS_URL=redis://localhost:6379/1 \
    python manage.py collectstatic --noinput 2>/dev/null || true

# Copy and setup entrypoint
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

# Railway sets PORT env var automatically
EXPOSE $PORT

ENTRYPOINT ["/entrypoint.sh"]

# Default command for Railway (ASGI with Uvicorn)
CMD exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 4 \
    --threads 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance \
    config.asgi:application

# ----------------------------------------------------------------------------
# STAGE 4: Celery Worker
# ----------------------------------------------------------------------------
FROM production as celery

USER root
# Install additional tools for Celery if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

USER appuser

# Skip migrations for Celery workers (web handles this)
ENV SKIP_MIGRATIONS=1

# Celery worker command
CMD exec celery -A config.celery worker \
    -l info \
    -Q whatsapp,orders,payments,langflow,automation,campaigns,messaging,default \
    --concurrency=4 \
    --max-tasks-per-child=1000

# ----------------------------------------------------------------------------
# STAGE 5: Celery Beat (Scheduler)
# ----------------------------------------------------------------------------
FROM production as beat

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

USER appuser

ENV SKIP_MIGRATIONS=1

# Celery beat command with database scheduler
CMD exec celery -A config.celery beat \
    -l info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --max-interval=300

# ----------------------------------------------------------------------------
# STAGE 6: Langflow Dedicated Worker
# ----------------------------------------------------------------------------
FROM production as langflow-worker

USER appuser

ENV SKIP_MIGRATIONS=1

# Dedicated worker for Langflow queue only
CMD exec celery -A config.celery worker \
    -l info \
    -Q langflow \
    -n langflow@%h \
    --concurrency=2 \
    --max-tasks-per-child=50
