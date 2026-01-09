#!/usr/bin/env python
import os
import subprocess
import sys

set -e

echo "Starting Application Entrypoint Script"
echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating admin user..."
python manage.py create_admin || echo "Admin already exists"

port = os.environ.get('PORT', '8080')
print(f"=== Starting gunicorn on port {port} ===")

subprocess.run([
    sys.executable, '-m', 'gunicorn',
    'config.wsgi:application',
    '--bind', f'0.0.0.0:{port}',
    '--workers', '1',
    '--timeout', '120',
    '--access-logfile', '-',
    '--error-logfile', '-'
])
