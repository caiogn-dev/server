web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A config worker -l info -Q automation,whatsapp,orders,payments,langflow
beat: celery -A config beat -l info
