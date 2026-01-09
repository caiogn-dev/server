#!/usr/bin/env python
import os
import subprocess
import sys

port = os.environ.get('PORT', '8080')

# Make migrations
print("=== Creating database migrations ===")
makemigrations_result = subprocess.run([
    sys.executable, 'manage.py', 'makemigrations', '--noinput'
])
if makemigrations_result.returncode != 0:
    print("WARNING: makemigrations failed, but continuing...")

# Run migrations
print("=== Applying database migrations ===")
migrate_result = subprocess.run([
    sys.executable, 'manage.py', 'migrate', '--noinput'
])
if migrate_result.returncode != 0:
    print("WARNING: migrate failed, but continuing...")

# Collect static files (optional, uncomment if needed)
# print("=== Collecting static files ===")
# subprocess.run([sys.executable, 'manage.py', 'collectstatic', '--noinput'])

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
