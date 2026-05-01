# Cross-Project Alignment — 2026-04-30

Scope: `server2`, `pastita-dash`, `ce-saladas`, Obsidian vault, and active planning docs.

## Current Source Of Truth

- `server2` is the domain/API source of truth.
- `CheckoutService` is the canonical storefront order factory.
- WhatsApp simple product carts now adapt into `CheckoutService` through a transient `StoreCart`.
- Mercado Pago production integration is real and remains wired through `CheckoutService.create_payment()`.
- `pastita-dash` is an operational dashboard; it should call backend APIs and render real returned state, not compute sensitive business rules.
- `ce-saladas` is the customer storefront for Cê Saladas; catalog, cart, checkout, delivery fee, payment status, and order detail should come from `server2`.

## What Is Already Aligned

- P0 migration drift for `agents` is closed locally via migration `0007`.
- P1 smoke contracts cover:
  - `GET /api/v1/stores/{slug}/catalog/`
  - `GET /api/v1/public/{slug}/catalog/`
  - guest checkout
  - order by token
  - customer order detail with token
  - delivery-fee quote normalization
- P2 started:
  - WhatsApp simple carts call `CheckoutService.create_order()`.
  - Pre-calculated WhatsApp delivery fees are supported.
  - WhatsApp metadata is preserved on orders.
  - Email automation is skipped for WhatsApp bot orders.
- `pastita-dash` P0 contract fixes are local:
  - automation stats/settings now call `/whatsapp/automation/...`
  - intent stats accepts `intent_type`
  - WhatsApp token rotation/business profile calls real endpoints
  - paginated-envelope normalization exists for orders/conversations/payments
  - analytics tabs now render tab-specific reports

## Highest Priority Gaps

### P0 — Commit And Deploy Hygiene

Do not start broad cleanup before the dirty worktree is split.

Current local work spans multiple domains:

- WhatsApp/LLM race fixes and order session fixes.
- CheckoutService/WhatsApp P2 adapter.
- Contract tests and migration.
- `pastita-dash` service/page contract fixes.
- Documentation.

Required next move:

1. Split commits by domain.
2. Run the same validation per domain.
3. Deploy only the intended backend/frontend bundles.
4. Record rollback notes.

### P1 — Contract Coverage Still Missing

- Add a real Flutter/mobile checkout payload fixture against `/api/v1/stores/{slug}/checkout/`.
- Add delivery examples for Palmas zones and out-of-area responses.
- Add order receipt/printing contract for custom salad ingredients so receipts do not render raw JSON.

### P2 — Checkout Canonicalization Remaining

- Legacy WhatsApp direct order creation remains only for `price_source=whatsapp_catalog` with arbitrary `unit_price`.
- To remove the fallback, either:
  - model external per-item price overrides in cart/order creation, or
  - map WhatsApp catalog prices back to canonical product/variant prices before checkout.
- Add a PIX smoke/regression path that verifies Mercado Pago stays wired through `CheckoutService.create_payment()` in the deployed environment.
- Add user-facing WhatsApp response coverage for stock validation failures.

### P3 — Geo And Legacy Cleanup

Decision:

- Google is the canonical maps/geo provider.
- Backend `GeoService` owns geocode, reverse geocode, route, delivery quote, fixed zones, and out-of-area reason.
- Frontends may render Google Maps and collect address/location UX, but final delivery price belongs to backend.

Current mismatch:

- `server2` direction is backend-owned geo/delivery through `GeoService` and Google.
- `ce-saladas` and `pastita-3d` were migrated to Google Maps JS rendering plus backend-owned GeoService calls.
- `ce-saladas` also has Google Maps rendering helpers and backend geocode/reverse-geocode calls.

Required direction:

- Remove remaining legacy compatibility names after test/import inventory.
- Keep compatibility shims only where still needed for safe transition.
- Frontend env docs now point to `NEXT_PUBLIC_GOOGLE_MAPS_KEY`; backend env points to `GOOGLE_MAPS_KEY`.

### P4 — pastita-dash Operational Cleanup

Do not redesign the dashboard yet.

Remaining cleanup:

- Create one shared chat/realtime adapter before removing duplicated clients.
- Current duplicate/parallel surfaces include:
  - `WhatsAppWsContext`
  - `WebSocketContext`
  - `useWhatsAppWS`
  - `useRealtime`
  - channel-specific WS hooks
  - reusable chat components
- Keep unsupported WhatsApp backend actions explicit in UI/service errors.
- Extend `normalizePaginatedEnvelope()` to any remaining list services that still assume only one backend shape.

### P5 — Webhook Idempotency

- Central webhook dispatcher checks duplicates in code, but `WebhookEvent.event_id` is indexed, not unique.
- Outbox has idempotency-key indexes, but inbound webhook event uniqueness is not DB-enforced.
- Before adding a uniqueness migration, inspect production duplicates by `(provider, event_id)` to avoid migration failure.

## Documentation Corrections Needed

- Obsidian `Ecossistema Pastita` should mention current dirty local state and P2 status.
- Obsidian `server2 - API e Contratos` should include `/stores/customer/orders/{id}/?token=...` as the customer-safe detail endpoint and mark global maps as backend-owned compatibility.
- Obsidian `pastita-dash` should no longer say the repo is clean; it has active local contract fixes.
- `pastita-dash/00_START_HERE.md` is historical. It should point to the current contract matrix and warn that Chakra guidance is legacy.
- `ce-saladas/README.md` now says `server2` and Google/backend geo. `pastita-3d` also follows the same rule.

## Validation Baseline From This Session

- `server2`: `python manage.py check` passed.
- `server2`: `python manage.py makemigrations --check --dry-run` reported no changes.
- `server2`: `python manage.py test tests.test_whatsapp_order_service tests.test_checkout_service apps.stores.tests.test_smoke_contracts apps.automation.tests.test_pipeline --keepdb -v 2` passed, 80 tests.
- `pastita-dash`: `npm run build` passed after local contract fixes.
