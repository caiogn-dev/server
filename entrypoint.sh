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

print(f"=== Starting daphne (ASGI) on port {port} ===")

subprocess.run([
    sys.executable, '-m', 'daphne',
    '-b', '0.0.0.0',
    '-p', str(port),
    '--proxy-headers',
    '--access-log', '-',
    'config.asgi:application'
])
