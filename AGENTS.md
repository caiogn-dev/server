# Server (Backend) — Repository Knowledge

Django backend for the Pastita/CE Saladas ecosystem. Multi-tenant e-commerce, WhatsApp/Instagram messaging, AI automation, and handover protocol.

## Tech Stack

- Python 3.12 / Django 4.x + Django REST Framework
- Django Channels 4.x (WebSocket) + SSE fallback
- PostgreSQL (production) / SQLite (development)
- Redis — channels layer, Celery broker, caching
- Celery + Celery Beat — background and periodic tasks
- Langchain — AI agents (OpenAI, Anthropic, Ollama, Kimi/Moonshot)
- drf-spectacular — auto-generated OpenAPI docs

## Authentication

**DRF Token Authentication only** (not JWT).

```
Authorization: Token <token>
```

Public endpoints (`/api/v1/public/`) use `AllowAny` with `AnonRateThrottle` (60 req/min).

## Active Apps

| App | Key Models |
|---|---|
| `apps.core` | User, CSRF, DashboardStats, SSE |
| `apps.stores` | Store, StoreProduct, StoreCategory, StoreOrder, StoreCart, Coupon, DeliveryZone |
| `apps.public_api` | AllowAny views wrapping stores models |
| `apps.whatsapp` | WhatsAppAccount, WhatsAppMessage, WebhookService, Flow |
| `apps.instagram` | InstagramAccount, InstagramMessage |
| `apps.messaging` | MessengerAccount, MessengerMessage (unified messaging) |
| `apps.conversations` | Conversation, Message, ConversationParticipant |
| `apps.handover` | ConversationHandover, HandoverRequest, HandoverLog |
| `apps.automation` | CompanyProfile, AutoMessage, CustomerSession, AutomationLog, AgentFlow |
| `apps.agents` | Agent, AgentConversation, AgentMessage |
| `apps.marketing` | Campaign, Template, Subscriber, EmailLog |
| `apps.campaigns` | WhatsApp broadcast Campaign, CampaignRecipient |
| `apps.notifications` | Notification |
| `apps.users` | UserProfile |
| `apps.audit` | AuditLog |
| `apps.webhooks` | WebhookDispatcher, WhatsAppHandler |

## API Base

- Main API: `/api/v1/`
- Public (no auth): `/api/v1/public/`
- Docs: `/api/docs/` (Swagger), `/api/redoc/`, `/api/schema/`
- SSE: `/api/sse/`

## Store Endpoints (Storefront Contract)

```
GET  /api/v1/stores/{slug}/                → Store detail
GET  /api/v1/stores/{slug}/catalog/        → Full catalog
GET  /api/v1/stores/{slug}/cart/           → Cart
POST /api/v1/stores/{slug}/cart/add/       → Add to cart
POST /api/v1/stores/{slug}/checkout/       → Place order
GET  /api/v1/stores/orders/by-token/{t}/  → Public order status
GET  /api/v1/stores/maps/geocode/         → Address geocoding
```

## Public API (AllowAny — storefronts)

```
GET /api/v1/public/{slug}/                → Store detail
GET /api/v1/public/{slug}/catalog/        → Catalog
GET /api/v1/public/{slug}/categories/     → Categories
GET /api/v1/public/{slug}/products/       → Products (filter: ?category=, ?search=)
GET /api/v1/public/{slug}/products/{id}/  → Product detail
GET /api/v1/public/{slug}/availability/   → { is_open, today, hours, operating_hours }
```

Rate limit: `AnonRateThrottle` 60 req/min for all public endpoints.
Checkout (`POST /checkout/`) has stricter `CheckoutThrottle`: 5 req/min per IP.

## WebSocket Endpoints

```
ws/notifications/
ws/chat/{conversation_id}/
ws/dashboard/
ws/stores/{store_slug}/orders/
ws/orders/{order_id}/
ws/whatsapp/{account_id}/
ws/whatsapp/dashboard/
ws/instagram/{account_id}/
```

## Handover Protocol (`apps.handover`)

Bot/Human mode for conversations. Fully installed.

```
POST /api/v1/handover/conversations/{uuid}/handover/bot/    → Switch to bot mode
POST /api/v1/handover/conversations/{uuid}/handover/human/  → Switch to human
GET  /api/v1/handover/conversations/{uuid}/handover/status/ → Current mode
GET  /api/v1/handover/conversations/{uuid}/handover/logs/   → History
```

## Automation API

```
GET/POST /api/v1/automation/companies/     → CompanyProfile CRUD
GET/POST /api/v1/automation/messages/      → AutoMessage CRUD
GET      /api/v1/automation/sessions/      → CustomerSession list
GET      /api/v1/automation/logs/          → AutomationLog list
GET      /api/v1/automation/unified/stats/ → Unified stats (requires ?account_id=)
```

Note: `AutoMessage` create uses `company_id` (UUID) not `company` FK in the request body.

## WhatsApp Webhook

```
GET  /webhooks/v1/whatsapp/   → Meta verification challenge (hub.mode=subscribe)
POST /webhooks/v1/whatsapp/   → Incoming events (messages, status updates)
GET  /webhooks/v1/whatsapp    → Same without trailing slash (Meta compatibility)
```

Signature validation: `HMAC-SHA256` using `WHATSAPP_APP_SECRET`. Helper: `apps.core.utils.verify_webhook_signature(payload_bytes, signature, secret)`.

## Key Architecture Notes

1. **Store is the tenant root** — All store-specific data is FK to `Store`. `CompanyProfile` (automation) is a 1:1 extension of `Store` (auto-created by signal on Store save).
2. **apps.messaging is canonical** — `apps/messaging/` is the unified messaging module for Messenger. There is no `apps/messenger/`.
3. **AgentFlow ≠ WhatsApp Flow** — `apps.automation.AgentFlow` handles custom AI conversation flows. `apps.whatsapp.Flow` is for WhatsApp native forms/templates. They are entirely different.
4. **Handover is apps.handover** — The canonical handover models live in `apps.handover`. `apps.conversations` does NOT have a duplicate HandoverModel.
5. **Guest cart** — `X-Cart-Key` header identifies guest cart sessions. Backend links cart to the header value for unauthenticated users.

## Core Commands

```bash
python manage.py runserver
python manage.py migrate
python manage.py test tests/
celery -A config worker -l info
celery -A config beat -l info
```

## Settings

- `config/settings/base.py` — shared defaults
- `config/settings/development.py` — SQLite, DEBUG, permissive CORS
- `config/settings/production.py` — PostgreSQL, WhiteNoise, strict CORS

Key env vars: `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `HERE_MAPS_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`.
