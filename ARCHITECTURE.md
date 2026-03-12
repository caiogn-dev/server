# Server Architecture

## Overview

`server` is the shared backend for:

- `ce-saladas` (customer storefront)
- `pastita-3d` (customer storefront)
- `pastita-dash` (operations dashboard)

The current API contract is centralized under `/api/v1/` with `stores` as the ecommerce core.

## Architecture Layers

- `config/`: Django settings, URL routing, ASGI/WSGI, Celery setup
- `apps/`: domain modules (stores, automation, messaging, etc.)
- `domain/`: domain entities/use-cases abstractions
- `infrastructure/`: external integrations and messaging infra

## Core Routing

Main router: `config/urls.py`

Key groups:

- `/api/v1/stores/` -> `apps.stores.urls`
- `/api/v1/auth/` and `/api/v1/` core auth/profile -> `apps.core.urls`, `apps.core.auth.urls`
- `/api/v1/whatsapp/`, `/instagram/`, `/messaging/`, `/conversations/`
- `/api/v1/automation/`, `/marketing/`, `/campaigns/`, `/audit/`, `/users/`, `/agents/`
- `/api/sse/` fallback event streams

## Ecommerce Contract (Current)

Storefront endpoints (canonical):

- `/api/v1/stores/{store_slug}/`
- `/api/v1/stores/{store_slug}/catalog/`
- `/api/v1/stores/{store_slug}/cart/`
- `/api/v1/stores/{store_slug}/checkout/`

Compatibility alias maintained:

- `/api/v1/stores/s/{store_slug}/...`

Global store endpoints:

- `/api/v1/stores/orders/`
- `/api/v1/stores/orders/by-token/{access_token}/`
- `/api/v1/stores/orders/{order_id}/payment-status/`
- `/api/v1/stores/maps/geocode/`
- `/api/v1/stores/maps/reverse-geocode/`

## Realtime

- WebSocket routes are defined in `apps.core.routing`
- Store/customer order channels:
  - `/ws/stores/{store_slug}/orders/`
  - `/ws/orders/{order_id}/`
- SSE fallback:
  - `/api/sse/orders/`
  - `/api/sse/whatsapp/`

## Settings Split

- `config/settings/base.py`: shared defaults, apps, middleware, DRF, CORS, caches, integrations
- `config/settings/development.py`: DEBUG mode, SQLite, permissive local CORS
- `config/settings/production.py`: security hardening, trusted origins, WhiteNoise
