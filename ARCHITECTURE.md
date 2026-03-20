# Server Architecture

## Overview

`server` is the shared Django backend for:

- `pastita-dash` — admin/operations dashboard (React)
- `pastita-3d` — Pastita customer storefront (Next.js)
- `ce-saladas` — CE Saladas customer storefront (Next.js)

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | Django 4.x + Django REST Framework |
| Realtime | Django Channels 4.x (WebSocket + SSE fallback) |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Cache/Broker | Redis (channels layer + Celery broker + caching) |
| Async tasks | Celery + Celery Beat |
| Auth | DRF Token Authentication (not JWT) |
| AI | Langchain (multi-provider: OpenAI, Anthropic, Ollama, Kimi) |
| API docs | drf-spectacular (Swagger + ReDoc at `/api/docs/`) |

---

## Active Django Apps

| App | Purpose |
|---|---|
| `apps.core` | Auth helpers, CSRF, dashboard stats, SSE, middleware, shared utilities |
| `apps.stores` | Multi-store e-commerce (products, catalog, cart, checkout, orders, payments, reports, delivery) |
| `apps.public_api` | AllowAny endpoints for storefronts (catalog, products, store detail) |
| `apps.whatsapp` | WhatsApp Business API integration (accounts, messaging, automation, webhook) |
| `apps.instagram` | Instagram Graph API integration |
| `apps.messaging` | Unified messaging API (Messenger, multi-channel) |
| `apps.conversations` | Conversation threads and unified inbox |
| `apps.handover` | Bot ↔ Human handover protocol |
| `apps.automation` | AI automation (CompanyProfile, AutoMessage, CustomerSession, AgentFlow) |
| `apps.agents` | AI agents (LangChain-backed, multi-model) |
| `apps.marketing` | Email marketing (campaigns, templates, subscribers) |
| `apps.campaigns` | WhatsApp broadcast campaigns |
| `apps.notifications` | Push/in-app notifications |
| `apps.users` | Unified user management |
| `apps.audit` | Audit trail |
| `apps.webhooks` | Centralized webhook dispatcher (Meta, MercadoPago, etc.) |

---

## URL Routing (`config/urls.py`)

### API v1 — Authenticated

```
/api/v1/core/                   → apps.core.urls
/api/v1/auth/                   → apps.core.auth.urls
/api/v1/stores/                 → apps.stores.urls
/api/v1/notifications/          → apps.notifications.urls
/api/v1/whatsapp/               → apps.whatsapp.urls
/api/v1/instagram/              → apps.instagram.urls
/api/v1/messaging/              → apps.messaging.urls
/api/v1/conversations/          → apps.conversations.urls
/api/v1/automation/             → apps.automation.urls
/api/v1/handover/               → apps.handover.urls
/api/v1/users/                  → apps.users.urls
/api/v1/agents/                 → apps.agents.urls
/api/v1/marketing/              → apps.marketing.urls
/api/v1/campaigns/              → apps.campaigns.urls
/api/v1/audit/                  → apps.audit.urls
```

### Public API — AllowAny (storefronts)

```
/api/v1/public/{store_slug}/              → Store detail
/api/v1/public/{store_slug}/catalog/      → Full catalog (categories + products)
/api/v1/public/{store_slug}/categories/   → Category list
/api/v1/public/{store_slug}/products/     → Product list (filterable)
/api/v1/public/{store_slug}/products/{id}/→ Product detail
```

### E-commerce Storefront Endpoints (auth optional)

```
/api/v1/stores/{store_slug}/              → Store detail
/api/v1/stores/{store_slug}/catalog/      → Full catalog
/api/v1/stores/{store_slug}/cart/         → Cart (guest via X-Cart-Key)
/api/v1/stores/{store_slug}/checkout/     → Place order
/api/v1/stores/{store_slug}/delivery-fee/ → Calculate fee
/api/v1/stores/{store_slug}/validate-coupon/ → Coupon validation
/api/v1/stores/{store_slug}/route/        → HERE route calculation
/api/v1/stores/orders/by-token/{token}/   → Public order status
/api/v1/stores/maps/geocode/              → Address geocoding
/api/v1/stores/maps/reverse-geocode/      → Reverse geocode
```

### Webhooks

```
/webhooks/v1/whatsapp/          → WhatsApp Business (GET=verify, POST=events)
/webhooks/v1/whatsapp           → Same (Meta sends without trailing slash)
/webhooks/payments/mercadopago/ → MercadoPago payment events
```

### API Docs

```
/api/schema/     → OpenAPI schema (JSON)
/api/docs/       → Swagger UI
/api/redoc/      → ReDoc
```

---

## WebSocket Routes (`apps/core/routing.py`)

```
ws/notifications/                          → NotificationConsumer
ws/chat/{conversation_id}/                 → ChatConsumer
ws/dashboard/                             → DashboardConsumer
ws/automation/                            → AutomationConsumer
ws/stores/{store_slug}/orders/            → StoreOrdersConsumer
ws/orders/{order_id}/                     → CustomerOrderConsumer
ws/whatsapp/{account_id}/                 → WhatsAppConsumer
ws/whatsapp/dashboard/                    → WhatsAppDashboardConsumer
ws/instagram/{account_id}/               → InstagramConsumer
```

### SSE Fallback (`/api/sse/`)

```
/api/sse/orders/       → OrderSSEView
/api/sse/whatsapp/     → WhatsAppSSEView
/api/sse/health/       → WebSocketHealthCheckView
```

---

## Authentication

- **DRF Token Auth**: `Authorization: Token <token>`
- Login: `POST /api/v1/auth/login/`
- Logout: `POST /api/v1/auth/logout/`
- Register: `POST /api/v1/auth/register/`
- Profile: `GET/PATCH /api/v1/users/profile/`
- CSRF token: `GET /api/v1/core/csrf/`

All dashboard endpoints require `Authorization: Token <token>`.
Public storefront endpoints (`/api/v1/public/`) use `AllowAny` with rate limiting.

---

## Settings Split

| File | Purpose |
|---|---|
| `config/settings/base.py` | Shared defaults, all INSTALLED_APPS, DRF config, CORS, Redis, Celery, integrations |
| `config/settings/development.py` | DEBUG=True, SQLite, permissive CORS, console email backend |
| `config/settings/production.py` | Security hardening, PostgreSQL, WhiteNoise, trusted origins |

Key settings:
- `WHATSAPP_APP_SECRET` — HMAC signature validation for WhatsApp webhooks
- `WHATSAPP_WEBHOOK_VERIFY_TOKEN` — Meta verification token
- `HERE_MAPS_API_KEY` — Geocoding and routing
- `CELERY_BROKER_URL` — Redis URL (default: `redis://localhost:6379/0`)

---

## Celery Tasks

Registered via `config/celery.py`. Beat schedule handles:
- Periodic WhatsApp message processing
- Automation trigger checks
- Campaign broadcasts
- Email queue processing
- Cache warming
- Audit log cleanup

---

## Key Design Decisions

1. **Store as single source of truth** — `Store` model is the central tenant entity. `CompanyProfile` (automation) is 1:1 with `Store`.
2. **DRF Token, not JWT** — The frontend uses `Authorization: Token xxx`. Do not switch to JWT without coordinating with all frontends.
3. **Guest cart via `X-Cart-Key`** — Unauthenticated users have their cart session identified by a `guest_cart_key` stored in localStorage. The header `X-Cart-Key` is attached to every cart request.
4. **Handover protocol** — `apps.handover` manages Bot/Human mode transitions. `ConversationHandover` model tracks state; WebSocket events notify the dashboard.
5. **Webhook security** — All inbound webhook payloads are validated with HMAC-SHA256 (`apps.core.utils.verify_webhook_signature`).

---

## Commands

```bash
# Start dev server
python manage.py runserver

# Apply migrations
python manage.py migrate

# Run tests
python manage.py test tests/

# Celery worker
celery -A config worker -l info

# Celery beat (periodic tasks)
celery -A config beat -l info
```
