# ============================================================================
# PASTITA PLATFORM - MAKEFILE
# ============================================================================
# Common commands for development and deployment
# ============================================================================

.PHONY: help build up down logs shell migrate superuser test clean

# Default target
help:
	@echo "Pastita Platform - Available Commands"
	@echo "======================================"
	@echo ""
	@echo "Development:"
	@echo "  make build          - Build all Docker images"
	@echo "  make up             - Start all services"
	@echo "  make up-d           - Start all services in background"
	@echo "  make down           - Stop all services"
	@echo "  make down-v         - Stop and remove volumes (WARNING: data loss)"
	@echo "  make logs           - View logs from all services"
	@echo "  make logs-web       - View web service logs"
	@echo "  make logs-celery    - View celery logs"
	@echo ""
	@echo "Django Management:"
	@echo "  make shell          - Open Django shell"
	@echo "  make dbshell        - Open database shell"
	@echo "  make migrate        - Run database migrations"
	@echo "  make makemigrations - Create new migrations"
	@echo "  make superuser      - Create superuser"
	@echo "  make static         - Collect static files"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test           - Run tests"
	@echo "  make lint           - Run linting"
	@echo "  make format         - Format code"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          - Remove all containers and volumes"
	@echo "  make prune          - Prune Docker system"
	@echo "  make backup         - Backup database"
	@echo "  make restore        - Restore database from backup"
	@echo ""
	@echo "Railway Deploy:"
	@echo "  make railway-deploy - Deploy to Railway"
	@echo "  make railway-logs   - View Railway logs"

# ============================================================================
# BUILD & RUN
# ============================================================================

build:
	docker-compose build

up:
	docker-compose up

up-d:
	docker-compose up -d

down:
	docker-compose down

down-v:
	docker-compose down -v

# ============================================================================
# LOGS
# ============================================================================

logs:
	docker-compose logs -f

logs-web:
	docker-compose logs -f web

logs-celery:
	docker-compose logs -f celery

logs-langflow:
	docker-compose logs -f langflow

# ============================================================================
# DJANGO MANAGEMENT
# ============================================================================

shell:
	docker-compose exec web python manage.py shell

dbshell:
	docker-compose exec web python manage.py dbshell

migrate:
	docker-compose exec web python manage.py migrate

makemigrations:
	docker-compose exec web python manage.py makemigrations

superuser:
	docker-compose exec web python manage.py createsuperuser

static:
	docker-compose exec web python manage.py collectstatic --noinput

check:
	docker-compose exec web python manage.py check

# ============================================================================
# TESTING
# ============================================================================

test:
	docker-compose exec web python manage.py test

test-verbose:
	docker-compose exec web python manage.py test -v 2

test-app:
	docker-compose exec web python manage.py test $(APP)

# ============================================================================
# CELERY
# ============================================================================

celery-status:
	docker-compose exec celery celery -A config.celery inspect active

celery-purge:
	docker-compose exec celery celery -A config.celery purge

flower:
	@echo "Flower available at http://localhost:5555"
	@echo "Login: admin / admin"

# ============================================================================
# MAINTENANCE
# ============================================================================

clean:
	docker-compose down -v --rmi all --remove-orphans

prune:
	docker system prune -f
	docker volume prune -f

backup:
	@mkdir -p backups
	@docker-compose exec -T db pg_dump -U postgres pastita > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backup created in backups/"

restore:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backups/backup_YYYYMMDD_HHMMSS.sql"; \
		exit 1; \
	fi
	cat $(FILE) | docker-compose exec -T db psql -U postgres pastita

# ============================================================================
# RAILWAY
# ============================================================================

railway-deploy:
	cd .. && railway up

railway-logs:
	railway logs

railway-connect:
	railway connect

# ============================================================================
# LANGFLOW
# ============================================================================

langflow-open:
	@echo "Opening Langflow at http://localhost:7860"
	@open http://localhost:7860 || xdg-open http://localhost:7860 || echo "Open manually"

langflow-logs:
	docker-compose logs -f langflow

# ============================================================================
# UTILITIES
# ============================================================================

ps:
	docker-compose ps

exec-web:
	docker-compose exec web bash

exec-db:
	docker-compose exec db bash

update-deps:
	docker-compose exec web pip install -r requirements.txt
