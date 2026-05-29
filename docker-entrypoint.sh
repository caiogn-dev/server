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

# Executar Django migrations
echo "🔄 Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "🔄 Collecting static files..."
python manage.py collectstatic --noinput

# Database integrity check with auto-seed on failure
echo "🔍 Verificando integridade do banco de dados..."
if ! python manage.py db_healthcheck --auto-seed 2>/dev/null; then
    echo "⚠️  Auto-seed failed or stores missing, attempting seed..."
    python manage.py populate_ce_saladas_menu --force || true
    python manage.py populate_pastita_menu --force || true
    python manage.py populate_kero_kero_menu --force || true
    python manage.py populate_delivery_zones || true
    echo "✅ Seed automático completado"
fi

echo "✅ Iniciando Gunicorn..."

# Executar comando passado (gunicorn por padrão)
exec "$@"
