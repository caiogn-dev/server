# Server2 Duplication / Cleanup Audit — 2026-04-28

Read-only architecture audit across `server2`, `pastita-dash`, `ce-saladas`, and `ce-saladas-flutter`.

## Executive Summary

The biggest risk is not just code volume; it is duplicated ownership of the same production behaviors:

- Order creation exists through storefront checkout and WhatsApp order services.
- Delivery/geo logic exists in backend services and older frontend map services.
- WhatsApp/automation inbound can still enter newer `UnifiedService` and older automation tasks.
- Webhooks have central dispatcher paths and domain-specific paths with overlapping models.
- Frontend chat/upload/order contracts are split across duplicated clients and pages.
- `server2` has a large dirty worktree, including untracked migrations and new print models, so deployment must be sequenced carefully.

## Highest Priority Findings

### Critical — Mercado Pago central webhook path can fail

- Location: `apps/webhooks/handlers/mercadopago_handler.py`
- Problem: imports `apps.stores.services.mercadopago_service.MercadoPagoService`, but that service module/class is not present.
- Impact: `/webhooks/v1/mercadopago/` can fail at runtime while `/webhooks/payments/mercadopago/` follows a different working path.
- Safe action: centralize Mercado Pago handling in one service or make the central route delegate to the working stores webhook.

### High — Order creation is duplicated

- Locations: `apps/stores/services/checkout_service.py`, `apps/whatsapp/services/order_service.py`
- Problem: storefront and WhatsApp both construct orders, totals, items, freight/payment context and notifications through different paths.
- Impact: price, stock, Pix, custom salad/combo support and realtime events can diverge.
- Safe action: make `CheckoutService` the canonical order factory; keep WhatsApp order service as an adapter that builds a checkout payload.

### High — Inbound automation has old and new pipelines

- Locations: `apps/whatsapp/services/webhook_service.py`, `apps/automation/tasks/__init__.py`, `apps/automation/services/automation_service.py`
- Problem: active webhook uses `UnifiedService`, but legacy Celery task can still call older `AutomationService`.
- Impact: duplicate replies or old behavior, including old Pix/plain-text flows, can leak back if any legacy producer runs.
- Safe action: convert legacy task into a delegator/no-op with telemetry, then remove after usage is confirmed absent.

### High — Database constraints do not protect key race conditions

- Locations: `apps/stores/models/order.py`, `apps/stores/models/cart.py`, `apps/stores/models/product.py`, `apps/webhooks/models.py`
- Problems:
  - `order_number` uses random 4 digits with no retry.
  - active carts are not unique per store/user or store/session.
  - cart item uniqueness does not handle `variant=NULL` or options safely.
  - stock decrement can go negative under concurrency.
  - central webhook idempotency is not enforced by a unique constraint.
- Safe action: add constraints and retry logic in phased migrations, with data cleanup dry-runs first.

### High — Frontend chat and upload contracts are duplicated

- Locations: `pastita-dash/src/pages/whatsapp/WhatsAppInboxPage.tsx`, `pastita-dash/src/components/chat/ChatWindow.tsx`, `pastita-dash/src/context/WhatsAppWsContext.tsx`, `pastita-dash/src/hooks/useWhatsAppWS.ts`, `pastita-dash/src/services/*`
- Problem: dashboard has incompatible WhatsApp WebSocket clients, duplicated chat surfaces and multiple upload/form patterns.
- Impact: fixes land in one screen and fail in another; upload regressions like forced `application/json` can recur.
- Safe action: create a single `features/chat` API/realtime layer and shared `api.postForm()/patchForm()`.

## Canonical Ownership Decisions

Recommended targets:

- `Store`: tenant root.
- `CheckoutService`: canonical order creation.
- `GeoService` / backend delivery quote: canonical delivery price and routing.
- `apps.webhooks.WebhookEvent`: raw envelope/idempotency, if centralized.
- `apps.whatsapp.WebhookEvent`: domain processing record, only if explicitly documented as separate from raw envelope.
- `Conversation`: long-term canonical conversation entity; channel-specific message tables should point into it or be migrated behind it.
- `CampaignService` or `ScheduledMessage`: one campaign send path; legacy tasks should delegate.

## Code Dead Or Abandoned Candidates

Do not delete these blindly. First add usage logging or confirm no import/caller in production:

- `apps/whatsapp/services/automation_service.py`
- `apps/automation/tasks/unified_messaging_tasks.py`
- `apps/whatsapp/tasks/legacy_tasks.py` task-name compatibility exports
- flat store routes duplicated with nested store routes
- `HereMapsService` compatibility alias and old frontend HERE services
- dashboard mock-success methods for WhatsApp business profile, token rotation and billing

## Cleanup Plan

### Phase 0 — Freeze and inventory

- Snapshot what runs in production container versus Git.
- Split the dirty `server2` worktree into themed commits before broad deploys.
- Decide whether untracked migrations for conversations and printing are shipping now.

### Phase 1 — Contract matrix

- Document endpoints used by `ce-saladas`, `ce-saladas-flutter`, `pastita-dash`.
- Mark each endpoint `canonical`, `compat`, or `dead-candidate`.
- Start with checkout/cart/delivery/order status/WhatsApp messages/conversations/campaigns.

### Phase 2 — Order and delivery centralization

- Make WhatsApp order creation call the same backend order factory as storefront checkout.
- Keep delivery fee and route calculation backend-owned.
- Remove frontend-authoritative delivery calculation from new flows.

### Phase 3 — Webhook and automation convergence

- Fix Mercado Pago central route.
- Add database idempotency constraints.
- Convert legacy inbound automation tasks into delegators or no-op telemetry.
- Choose one campaign send path and make legacy task names wrappers.

### Phase 4 — Frontend service consolidation

- `pastita-dash`: one chat feature, one realtime client, one form upload helper.
- `ce-saladas`: split monolithic `storeApi.js` into storefront/cart/checkout/auth/orders/maps clients.
- Remove fake-success service methods or show explicit unsupported states.

### Phase 5 — Remove code with telemetry

- Add logs/counters to compatibility routes and legacy tasks.
- After two safe cycles without usage, remove dead candidates.
- Every removal needs a contract test for the canonical path.

## Persistent Agent Profiles

Use these files for future Codex or Claude sessions:

- `server2/docs/agents/server2-backend-general.md`
- `server2/docs/agents/server2-database-models.md`
- `server2/docs/agents/pastita-frontend-contracts.md`
- `server2/docs/agents/pastita-platform-orchestrator.md`

Claude Code wrappers:

- `server2/.claude/agents/server2-backend-general.md`
- `server2/.claude/agents/server2-database-models.md`
- `server2/.claude/agents/pastita-frontend-contracts.md`
- `server2/.claude/agents/pastita-platform-orchestrator.md`
