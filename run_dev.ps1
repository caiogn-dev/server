$ErrorActionPreference = "Stop"

$env:DJANGO_SETTINGS_MODULE = "config.settings.development"
$env:DEBUG = "True"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"

Write-Host "Using DJANGO_SETTINGS_MODULE=$env:DJANGO_SETTINGS_MODULE"
Write-Host "Running migrations..."
python manage.py migrate

Write-Host "Starting Django server at http://localhost:8000"
python manage.py runserver 0.0.0.0:8000
