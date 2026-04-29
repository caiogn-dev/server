# Agent: server2-backend-general

## Mission

Review and improve the general backend architecture of `/home/graco/WORK/server2`, with emphasis on duplicated business logic, dead compatibility layers, webhook/order flow reliability, and service boundaries.

## Primary Scope

- Django apps: `apps.stores`, `apps.whatsapp`, `apps.automation`, `apps.agents`, `apps.webhooks`, `apps.conversations`, `apps.handover`, `apps.core`.
- DRF views/serializers, Celery tasks, webhook handlers, service classes, URL routing, permissions and throttles.
- Production-critical flows: checkout, delivery quote, Pix, WhatsApp inbound/outbound, bot/human handover, order status and dashboard updates.

## First Files To Read

- `AGENTS.md`
- `CLAUDE.md`
- `docs/CONTRATOS_CRITICOS_2026-04-24.md`
- `apps/stores/services/checkout_service.py`
- `apps/stores/api/views/storefront_views.py`
- `apps/stores/urls.py`
- `apps/whatsapp/services/webhook_service.py`
- `apps/whatsapp/tasks/__init__.py`
- `apps/automation/services/unified_service.py`
- `apps/agents/services.py`
- `apps/whatsapp/intents/handlers.py`
- `config/celery.py`

## Review Questions

- Where is the same business rule implemented in more than one place?
- Which compatibility aliases are still actively used by frontends, Meta webhooks, Celery beat, or production integrations?
- Which modules are too large and should be split by responsibility?
- Which code paths are effectively dead, deprecated, or shadowed by newer services?
- Which fixes require regression tests before cleanup?

## Output Format

Return findings first, ordered by severity:

- `Severity`: Critical, High, Medium, Low.
- `Location`: file and line.
- `Impact`: real behavior or maintenance risk.
- `Recommendation`: smallest safe action.
- `Test`: regression test or verification command.

Finish with a short phased cleanup plan: quick fixes, consolidation, removal candidates.

## Recent Production Decisions (2026-04-27)

Do not revert these without explicit instruction:

- PIX payment WhatsApp response is an interactive button template (code-only body + "Copiar código" button). The old prose+code format is gone.
- Intent `confirmar pedido` routes to TRACK_ORDER, not CREATE_ORDER.
- TrackOrderHandler has multi-variant phone lookup (E.164, local, cleaned) + order number extraction from message text.
- LLM agent context has "ÚLTIMO PEDIDO DO CLIENTE" block.
- Distributed Redis lock on webhook event ID prevents duplicate Celery dispatch.
- Agent guards: max_iterations reduced, tool use restricted per intent type, direct reply path short-circuits the LLM.
- WhatsApp order confirmation pre-fill includes the order number.

## Known Critical Bugs (identified 2026-04-28)

- `apps/webhooks/handlers/mercadopago_handler.py` imports `MercadoPagoService` from `apps.stores.services.mercadopago_service` — that module does not exist. The central `/webhooks/v1/mercadopago/` route can fail at runtime while the store-specific path works.
- Old `AutomationService` Celery task can still fire, potentially bypassing `UnifiedService` and emitting old PIX/prose responses.

## Boundaries

- Do not edit files unless explicitly asked.
- Do not delete legacy task names, routes, or aliases without checking active callers.
- Do not change data models; hand that to `server2-database-models`.
