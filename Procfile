web: python entrypoint.sh
worker: celery -A config worker -l info -Q automation,whatsapp,orders,payments,langflow
beat: celery -A config beat -l info
