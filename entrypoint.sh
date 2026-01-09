#!/usr/bin/env python
import os
import subprocess
import sys

set -e

print(f"Starting Application Entrypoint Script")
print("Running migrations...")
python manage.py migrate --noinput

print("Creating admin user...")
python manage.py create_admin || print("Admin already exists")

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
