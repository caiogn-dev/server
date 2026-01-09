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

# Collectstatic with a dummy secret key (will use real one at runtime)
RUN SECRET_KEY=build-time-secret python manage.py collectstatic --noinput

EXPOSE 8000

# Startup: migrate, create admin, then run gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput 2>&1 || echo 'Migration failed'; python manage.py create_admin 2>&1 || echo 'Admin creation skipped'; exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 --log-level info"]
