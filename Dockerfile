FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs staticfiles

# Create non-root user and fix permissions
RUN addgroup --system appuser \
    && adduser --system --ingroup appuser appuser \
    && chown -R appuser:appuser /app

# Copy and setup entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && chown appuser:appuser /entrypoint.sh

USER appuser

# Collectstatic with build-time settings to satisfy production checks
RUN DJANGO_ALLOWED_HOSTS=localhost DJANGO_SECRET_KEY=build-time-secret python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 4 --threads 4 --worker-class uvicorn.workers.UvicornWorker --access-logfile - --error-logfile - --capture-output --enable-stdio-inheritance config.asgi:application"]
