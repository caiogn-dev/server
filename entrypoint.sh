#!/usr/bin/env python
"""
Production entrypoint for Railway deployment.
DO NOT run makemigrations in production - migrations should be committed to git.
"""
import os
import subprocess
import sys

port = os.environ.get('PORT', '8080')

# Run migrations only (DO NOT run makemigrations in production)
print("=== Applying database migrations ===")
migrate_result = subprocess.run([
    sys.executable, 'manage.py', 'migrate', '--noinput'
])
if migrate_result.returncode != 0:
    print("ERROR: migrate failed!")
    sys.exit(1)

# Setup Pastita store if not exists
print("=== Setting up Pastita store ===")
setup_result = subprocess.run([
    sys.executable, 'manage.py', 'setup_pastita_store'
])
if setup_result.returncode != 0:
    print("WARNING: setup_pastita_store had issues, but continuing...")

# Collect static files
print("=== Collecting static files ===")
subprocess.run([sys.executable, 'manage.py', 'collectstatic', '--noinput'])

print(f"=== Starting daphne (ASGI) on port {port} ===")

subprocess.run([
    sys.executable, '-m', 'daphne',
    '-b', '0.0.0.0',
    '-p', str(port),
    '--proxy-headers',
    '--access-log', '-',
    'config.asgi:application'
])
