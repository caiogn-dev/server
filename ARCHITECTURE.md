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
/api/v1/stores/orders/by-token/{token}/   → Public order detail/status for mobile post-checkout
/api/v1/stores/maps/geocode/              → Address geocoding
/api/v1/stores/maps/reverse-geocode/      → Reverse geocode
```

Mobile note, 2026-04-26:

- `ce-saladas-flutter` must prefer `/api/v1/stores/orders/by-token/{token}/` for OrderDetail when it has `access_token`.
- Avoid using `/api/v1/stores/orders/{id}/` for customer mobile detail. That path conflicts with the admin `StoreOrderViewSet` router because router URLs are included before public customer order paths.
- Long-term fix: create a namespaced mobile/customer order detail route that cannot conflict with admin routers, for example `/api/v1/mobile/stores/{slug}/orders/{id}/` or `/api/v1/stores/customer/orders/{id}/` with explicit auth/token behavior and tests.

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

## WhatsApp Order Creation Flow

When a customer completes checkout via WhatsApp:

```
UnifiedService.process_message()
  → deterministic intent handler (_handle_payment_confirmation, etc.)
  → WhatsAppOrderService.create_order_from_cart()
      ├── Validates items, resolves StoreProduct
      ├── Creates StoreOrder + StoreOrderItem records
      ├── Decrements stock via F() expression (atomic, only when track_stock=True)
      ├── Calls CheckoutService.create_payment() for PIX/card flows
      ├── Builds structured delivery_address via _build_delivery_address()
      │     maps HERE Maps keys (houseNumber, district, stateCode, postalCode)
      │     to frontend-standard keys (number, neighborhood, state, zip_code)
      └── Dispatches broadcast_order_event() via transaction.on_commit
```

`CustomerSession.cart_data` holds all conversational state including `delivery_address_components`
(populated by `SessionManager.save_delivery_address_info()`), which flows into the order's
`delivery_address` JSON field.

---

## WhatsApp Notification Dispatch (Order Status)

Single notification path — no duplicate sends:

```
StoreOrder.update_status(new_status, notify=True)
  └── saves model, calls send_status_webhook + _trigger_status_email_automation
      (does NOT call _trigger_status_whatsapp_notification directly)

post_save signal (apps/automation/signals.py)
  └── transaction.on_commit → notify_order_status_change.delay(order_id, status)

notify_order_status_change (Celery task)
  ├── tries AutoMessage.objects.get(event_type=event, is_active=True)
  │     → renders template → WhatsAppAPIService.send_text_message()
  └── except AutoMessage.DoesNotExist:
        → order._trigger_status_whatsapp_notification(new_status)  [fallback]
```

**Why**: before this design, `update_status()` called both the direct method AND the
signal-triggered task, causing duplicate messages for stores with AutoMessage templates.

---

## Delivery Fee Calculation

Single source of truth: `CheckoutService._calculate_dynamic_fee(store, distance_km)`.

Formula: `fee = max(base_fee, base_fee + (distance - free_km) * per_km_rate)`, capped at `max_fee`.
All values configurable via `Store.metadata` keys (`delivery_base_fee`, `delivery_fee_per_km`,
`delivery_free_km`, `delivery_max_fee`). Falls back to `store.default_delivery_fee`.

`HereMapsService.calculate_delivery_fee()` delegates to this method rather than maintaining
its own formula, preventing divergence between delivery-zone validation and actual charge.

---

## Key Design Decisions

1. **Store as single source of truth** — `Store` model is the central tenant entity. `CompanyProfile` (automation) is 1:1 with `Store`.
2. **DRF Token, not JWT** — The frontend uses `Authorization: Token xxx`. Do not switch to JWT without coordinating with all frontends.
3. **Guest cart via `X-Cart-Key`** — Unauthenticated users have their cart session identified by a `guest_cart_key` stored in localStorage. The header `X-Cart-Key` is attached to every cart request.
4. **Handover protocol** — `apps.handover` manages Bot/Human mode transitions. `ConversationHandover` model tracks state; WebSocket events notify the dashboard.
5. **Webhook security** — All inbound webhook payloads are validated with HMAC-SHA256 (`apps.core.utils.verify_webhook_signature`).
6. **Single broadcast path** — `broadcast_order_event()` in `apps.stores.services.realtime_service` is the only place that sends WebSocket events for orders. Never use `channel_layer` directly from order-creation code.
7. **Stock decrement via F()** — `StoreProduct.stock_quantity` is always decremented with `F('stock_quantity') - qty` inside `update()` to avoid read-modify-write races on concurrent orders.
8. **Provider-agnostic geo layer** — `GeoService` (Google Maps primary, haversine fallback) is the single geo interface. The legacy `HereMapsService` is now a thin subclass that delegates to `GeoService` for backward compat. All new code imports `geo_service` from `apps.stores.services.geo`.
9. **External delivery provider abstraction** — `DeliveryProvider` ABC in `apps/stores/services/delivery_provider/` decouples order dispatch from the provider. Current: `TocaDeliveryProvider` (live) + `InternalDeliveryProvider` (no-op). New providers: add a class, register in `get_delivery_provider()`.

---

## Geo Service Layer (Google Maps)

Provider-agnostic geo service. Google Maps is the primary backend; haversine is the fallback for routes when the API fails.

```
apps/stores/services/geo/
    contract.py          — TypedDict contracts (GeocodeResult, RouteResult)
    google_provider.py   — Low-level Google Maps HTTP client
    service.py           — GeoService: geocode, reverse_geocode, route, autosuggest,
                           validate_delivery_address, calculate_delivery_fee
    __init__.py          — exports geo_service singleton

apps/stores/services/here_maps_service.py
    HereMapsService(GeoService)  — backward-compat subclass (do not use in new code)
```

**Caching**: MD5-keyed Redis cache. Routes and geocodes: 24h TTL. Isolines: 6h TTL.

**Delivery fee resolution order**:
1. Fixed-price zone match (keyword-based in `store.metadata['fixed_price_zones']`)
2. `StoreDeliveryZone` DB records (ordered by `min_km`)
3. `CheckoutService._calculate_dynamic_fee()` (dynamic formula)
4. `store.default_delivery_fee` (fallback when no coordinates)

---

## External Delivery Provider (Toca Delivery)

See full spec in `docs/TOCA_DELIVERY_INTEGRATION.md`.

**Flow**:
1. `StoreOrder.status → 'confirmed'` triggers signal `on_order_confirmed_dispatch_toca`
2. Signal enqueues Celery task `dispatch_order_to_toca_delivery`
3. Task calls `TocaDeliveryProvider.create(store, order)` → `POST /corridas`
4. `StoreOrder.external_delivery_*` fields updated with corrida ID/code/URL
5. Celery Beat task `sync_toca_delivery_statuses` (60s) polls active corridas
6. Status mapped: `em_rota → out_for_delivery`, `entregue → delivered`
7. Webhook receiver at `/webhooks/v1/toca-delivery/` handles push updates (future)

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
