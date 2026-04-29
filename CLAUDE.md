# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Pastita** — Multi-tenant e-commerce backend with AI-powered WhatsApp/Instagram automation. Serves three frontends: `pastita-3d` and `ce-saladas` (Next.js storefronts) and `pastita-dash` (React admin dashboard).

**Stack**: Django 4 + DRF + Django Channels (WebSocket) + Celery + Redis + PostgreSQL + Langchain (multi-LLM)

## Current Context - 2026-04-26

Canonical continuation doc: `/home/graco/WORK/PASTITA_ESTADO_PLANEJAMENTO_2026-04-24.md`.

Recent production-facing decisions:

- `server2` is the canonical backend for `ce-saladas-flutter`.
- WhatsApp OTP mobile uses:
  - `POST /api/v1/auth/whatsapp/send/`
  - `POST /api/v1/auth/whatsapp/verify/`
  - Meta template `codigo_verificacao`
- OTP template sends the code in both body and URL/copy-code button parameters. Do not fall back to free text for OTP outside the 24h WhatsApp window.
- Placeholder emails like `{phone}@pastita.local` are internal identity fallbacks only. API/mobile display must not show them as real customer email/name.
- Customer profile display should prefer real `first_name/last_name`, `Conversation.contact_name`, or `UnifiedUser.name`; never expose `cliente_...` as user-facing name.
- Cê Saladas delivery/geo rules must stay centralized. Avoid duplicating fee logic between checkout, WhatsApp agent and geo services.
- WhatsApp agent `Caio` should ask for address/location to calculate delivery and must not expose internal fee rules or generate Pix before clear items exist.
- Flutter mobile order detail should prefer `GET /api/v1/stores/orders/by-token/{token}/` when the order list provides `access_token`. Avoid using `/api/v1/stores/orders/{id}/` for the customer mobile detail path because it currently conflicts with administrative store order routing.
- Long-term backend cleanup: create a clean mobile/customer namespace for order detail, status, tracking and reorder, then add contract tests so route ordering cannot break the app again.

Critical contracts:

- `docs/CONTRATOS_CRITICOS_2026-04-24.md`

Critical pending work:

1. Create/verify a dedicated mobile customer order API namespace for detail/status/tracking/reorder.
2. Support custom salad items from Flutter builder in checkout/order/receipt.
3. Add regression tests for OTP, delivery zones, route calculation, checkout payload, orders by token and agent guardrails.
4. Resolve Google vs HERE as the canonical geo provider in docs/env/service names.
5. Keep delivery-fee and route calculation as backend-owned truth; Flutter should never hardcode delivery prices.

## Commands

All commands run inside Docker containers via `make` or `docker-compose exec`:

```bash
# Start/stop
make up-d                          # Start all services (background)
make down                          # Stop services

# Django management
make migrate                       # Run migrations
make makemigrations                # Create new migrations
make shell                         # Django shell
make superuser                     # Create superuser

# Testing
make test                          # Run all tests
make test-verbose                  # Run tests with verbosity
make test-app APP=apps.stores      # Run tests for a specific app

# Without Docker (local dev)
python manage.py runserver
python manage.py test apps.stores
celery -A config.celery worker -l info
```

**Settings module**: `DJANGO_SETTINGS_MODULE=config.settings.development` (dev) or `config.settings.production`

## Architecture

### Tenant Model

`Store` is the root tenant. All store-specific data FKs to `Store`. `CompanyProfile` (in `apps.automation`) is auto-created 1:1 with `Store` and holds AI/automation config.

### App Responsibilities

| App | Responsibility |
|-----|---------------|
| `apps.core` | Auth endpoints, CSRF, SSE streaming, WebSocket routing, middleware |
| `apps.stores` | Full e-commerce: catalog, cart, checkout, orders, payments, delivery zones, coupons |
| `apps.public_api` | AllowAny endpoints for storefronts (`/api/v1/public/{store_slug}/`) |
| `apps.whatsapp` | WhatsApp Business API: accounts, messages, webhook, native Flows |
| `apps.instagram` | Instagram Graph API: accounts, messages, webhook |
| `apps.messaging` | Unified Messenger dispatcher (multi-channel abstraction) |
| `apps.conversations` | Conversation threads and unified inbox across channels |
| `apps.handover` | Bot ↔ human handover protocol |
| `apps.automation` | AI automation: `CompanyProfile`, `AutoMessage`, `CustomerSession`, `ScheduledMessage`, `AgentFlow` |
| `apps.agents` | Langchain AI agents — supports OpenAI, Anthropic, Kimi/Moonshot, Ollama |
| `apps.webhooks` | Central webhook dispatcher — validates HMAC-SHA256 signatures, routes to apps |
| `apps.campaigns` | WhatsApp broadcast campaigns |
| `apps.marketing` | Email campaigns via Resend |

### Request Flow

```
Storefront (public)     → /api/v1/public/{store_slug}/       (AllowAny)
Dashboard (auth)        → /api/v1/stores/{store_slug}/...    (Token auth)
WhatsApp webhook        → /webhooks/v1/whatsapp              → apps.webhooks → apps.automation → AI agent
Payments webhook        → /webhooks/payments/mercadopago/    → apps.webhooks
Real-time (WebSocket)   → ws/{type}/...                      (Django Channels)
Real-time (SSE)         → /api/sse/{type}/                   (fallback)
```

### Authentication

**DRF Token Auth only** — No JWT. Header: `Authorization: Token <token>`. Guest carts use `X-Cart-Key` header (stored in localStorage by frontends).

### Real-Time Architecture

Django Channels handles WebSocket connections. Key consumers:
- `ws/stores/{store_slug}/orders/` — Live order updates for dashboard
- `ws/whatsapp/{account_id}/` — Live WhatsApp messages
- `ws/chat/{conversation_id}/` — Chat interface
- `ws/dashboard/` — Aggregated dashboard stats

SSE fallback at `/api/sse/orders/` and `/api/sse/whatsapp/`.

### Celery Task Routing

Tasks are routed to named queues defined in `config/celery.py`:
- `whatsapp` queue — WhatsApp message sending/processing
- `agents` queue — LLM agent processing
- `automation` queue — Automation rule evaluation
- `campaigns` queue — Broadcast campaigns

Key periodic tasks (Celery Beat): pending PIX payments check (10min), abandoned carts (5min), scheduled messages (1min), Instagram token refresh (daily).

### WhatsApp Automation Pipeline

Incoming message → webhook → `apps.webhooks` dispatcher → `apps.automation` intent detection → `AgentFlow` or `AutoMessage` or LLM agent (`apps.agents`). The `CustomerSession` tracks cart/payment state per phone number. Bot↔human handover managed by `apps.handover`.

### MCP Server

`mcp_whatsapp_bot.py` is an MCP server for inspecting the WhatsApp automation pipeline. Register with:
```bash
claude mcp add whatsapp-bot -- python /path/to/mcp_whatsapp_bot.py
```
Provides tools: `debug_message`, `detect_intent`, `get_session`, `trace_conversation`, `pipeline_health`.

## Key Configuration

- **Settings split**: `config/settings/base.py` (shared) → `development.py` / `production.py`
- **ASGI**: `config/asgi.py` — Daphne server, Channels routing in `apps/core/routing.py`
- **Environment**: copy `.env.example` to `.env`. Required keys: `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`
- **API docs**: Swagger at `/api/docs/`, ReDoc at `/api/redoc/`, schema at `/api/schema/`

## Existing Documentation

- `ARCHITECTURE.md` — Detailed architecture with all URL routes and WebSocket consumers
- `AGENTS.md` — AI agent system knowledge base (models, endpoints, automation flow)
- `BACKEND_IMPLEMENTATION_GUIDE.md` — Implementation guide for backend features
