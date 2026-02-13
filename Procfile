web: python entrypoint.sh
worker: celery -A config.celery worker -l info -Q default,campaigns,automation,whatsapp,orders,payments,agents,marketing
beat: celery -A config.celery beat -l info
