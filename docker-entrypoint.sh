#!/bin/sh
set -e

echo "🔄 Docker entrypoint: Iniciando servidor..."

# Copiar imagens de seed para media (se existirem no host)
# Isso é feito via volume mount no docker-compose
# Exemplo: -v /home/graco/ftp-data/kerokero/generated:/seed/kero-kero:ro

if [ -d "/seed" ]; then
    echo "📸 Copiando imagens de seed..."

    # Kero Kero
    if [ -d "/seed/kero-kero" ]; then
        mkdir -p /app/media/stores/products/kero-kero
        cp -f /seed/kero-kero/*.webp /app/media/stores/products/kero-kero/ 2>/dev/null || true
        echo "  ✅ Kero Kero"
    fi

    # Cê Saladas
    if [ -d "/seed/ce-saladas" ]; then
        mkdir -p /app/media/stores/products/ce-saladas
        cp -f /seed/ce-saladas/*.webp /app/media/stores/products/ce-saladas/ 2>/dev/null || true
        echo "  ✅ Cê Saladas"
    fi

    # Pastita
    if [ -d "/seed/pastita" ]; then
        mkdir -p /app/media/stores/products/pastita
        cp -f /seed/pastita/*.webp /app/media/stores/products/pastita/ 2>/dev/null || true
        echo "  ✅ Pastita"
    fi

    chmod -R 755 /app/media/stores/products/
fi

# Init (migrate/collectstatic/seed) roda SÓ no web (RUN_INIT_TASKS=1).
# Antes os 3 containers (web/celery/beat) rodavam isto no boot ao mesmo tempo:
# - migrate concorrente = race quando há migration nova
# - collectstatic 3x = corrida no volume de estáticos
# - auto-seed --force em prod se o db_healthcheck falhar no boot (perigoso)
if [ "${RUN_INIT_TASKS:-0}" = "1" ]; then
    echo "🔄 Running migrations..."
    python manage.py migrate --noinput

    echo "🔄 Collecting static files..."
    python manage.py collectstatic --noinput

    echo "🔍 Verificando integridade do banco de dados..."
    if ! python manage.py db_healthcheck --auto-seed 2>/dev/null; then
        echo "⚠️  Auto-seed failed or stores missing, attempting seed..."
        python manage.py populate_ce_saladas_menu --force || true
        python manage.py populate_pastita_menu --force || true
        python manage.py populate_kero_kero_menu --force || true
        python manage.py populate_delivery_zones || true
        echo "✅ Seed automático completado"
    fi
else
    echo "⏭️  RUN_INIT_TASKS!=1 — pulando migrate/collectstatic/seed (init só no web)"
fi

echo "✅ Iniciando processo principal..."

# Executar comando passado (gunicorn por padrão)
exec "$@"
