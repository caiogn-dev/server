# Server (Backend) - Repository Knowledge

Django backend for Pastita/CE Saladas ecosystem with multi-store ecommerce, messaging, and automation.

## Tech Stack

- Django + Django REST Framework
- Django Channels (WebSocket/SSE fallback)
- PostgreSQL (default in production)
- Redis (cache, channels, Celery broker)
- Celery (async jobs)

## Active Apps

- `apps.stores`: multi-store catalog, cart, checkout, orders, payments, reports
- `apps.core`: auth helpers, middleware, shared endpoints, SSE
- `apps.whatsapp`: WhatsApp integration and automation
- `apps.instagram`: Instagram integration
- `apps.messaging`: unified messaging/Messenger endpoints
- `apps.conversations`: conversation threads and inbox APIs
- `apps.automation`: schedulers, flows, reports
- `apps.marketing`: email campaigns/templates/subscribers
- `apps.notifications`: notification APIs
- `apps.handover`: bot-human handover flow
- `apps.audit`: audit trail
- `apps.users`: unified user management
- `apps.agents`: AI agents and conversations
- `apps.webhooks`: centralized webhook dispatcher

## API Base

- Main API: `/api/v1/`
- Docs: `/api/docs/`, `/api/redoc/`, `/api/schema/`
- SSE: `/api/sse/`

## Store Endpoints

Canonical storefront contract:

- `/api/v1/stores/{store_slug}/`
- `/api/v1/stores/{store_slug}/catalog/`
- `/api/v1/stores/{store_slug}/cart/`
- `/api/v1/stores/{store_slug}/checkout/`

Compatibility alias kept for legacy clients:

- `/api/v1/stores/s/{store_slug}/...`

Global store resources:

- `/api/v1/stores/orders/`
- `/api/v1/stores/orders/by-token/{access_token}/`
- `/api/v1/stores/maps/geocode/`
- `/api/v1/stores/maps/reverse-geocode/`

## WebSocket Endpoints

- `/ws/dashboard/`
- `/ws/chat/{conversation_id}/`
- `/ws/stores/{store_slug}/orders/`
- `/ws/orders/{order_id}/`
- `/ws/whatsapp/{account_id}/`
- `/ws/whatsapp/dashboard/`

## Core Commands

```bash
python manage.py runserver
python manage.py migrate
python manage.py test
celery -A config worker -l info
```
