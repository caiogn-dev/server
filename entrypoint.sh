#!/usr/bin/env python
import os
import subprocess
import sys

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
