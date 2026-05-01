# Execution Status — 2026-04-29

This file tracks the current implementation sequence across `server2`, `pastita-dash`, `ce-saladas`, and `ce-saladas-flutter`.

## Completed Today

- `pastita-dash` manual order adjustment:
  - Commit `c368f2b` on `main`.
  - New order form supports no adjustment, discount, surcharge, amount, and reason.
  - Order detail and print views show manual surcharge from metadata.
  - Validation: `npm run build`.
- `server2` manual operational order adjustments:
  - Commit `1b7d60c` on `development`.
  - `StoreOrderCreateSerializer` accepts `discount`, `surcharge`, and `adjustment_reason`.
  - Validation: `py_compile apps/stores/api/serializers.py`, `manage.py check`.
- Mercado Pago central webhook P0:
  - Commit `124eccf` on `development`.
  - Removed broken import of missing `apps.stores.services.mercadopago_service`.
  - Central `/webhooks/v1/mercadopago/` now delegates payment status processing to `CheckoutService.process_payment_webhook`.
  - Hotfixed into running `pastita_web` and `pastita_celery`.
  - Validation:
    - `docker exec pastita_web python manage.py check`
    - direct handler smoke tests inside container
    - `POST /webhooks/v1/mercadopago/` synthetic safe payloads through nginx
    - `WebhookEvent` records completed with no failed central MP events
    - legacy `/webhooks/payments/mercadopago/` still returns controlled `no_payment_id`
- Frontend contract matrix:
  - Commit `dce5f20` on `development`.
  - Added `docs/agents/FRONTEND_CONTRACT_MATRIX_2026-04-29.md`.
- `ce-saladas` project notes:
  - Commit `c8eeafe` on `development`.
  - Added `CLAUDE.md`.
- Real production sanity:
  - User confirmed a normal Cê Saladas Pix order completed successfully after the webhook work.
- `pastita-dash` WhatsApp/dashboard contract cleanup:
  - Commit `fad2bce` on `main`.
  - Dashboard WebSocket now points to `/ws/whatsapp/dashboard/`.
  - Removed fake success responses for unsupported WhatsApp actions; they now fail explicitly through existing UI error handling.
  - Removed manual `multipart/form-data` headers from product/category/product-type uploads so Axios can set the boundary.
  - Validation: `npm run build`; `rg` confirmed no remaining manual multipart headers in `src`.

## Local Fix Not Yet Versioned

- `ce-saladas-flutter/lib/core/services/order_service.dart`
  - Changed payment status path from `/orders/{orderId}/payment-status/` to `/stores/orders/{orderId}/payment-status/`.
  - `flutter analyze` ran and failed only on existing info-level lints outside this file.
  - `ce-saladas-flutter` is not currently a git repository in this workspace, so this change cannot be committed here unless the project is initialized or copied to its owning repo.

## Current Highest-Priority Implementation Queue

1. Commit the persistent agent/roadmap documentation in `server2/docs/agents/`.
2. Split the remaining large `server2` dirty worktree by domain before any broad deploy:
   - print backend
   - WhatsApp/chat/media hotfixes
   - delivery/geo
   - checkout/order/cart
   - Meta Pixel/CAPI
   - tests/docs
3. Add remaining contract tests before deeper refactors:
   - Flutter checkout payload against `/stores/{slug}/checkout/`
   - delivery fee examples for Palmas fixed/dynamic zones
   - WhatsApp vs storefront equivalent totals before P2 order unification
4. Only after contracts are in place, start P2: make WhatsApp order creation call `CheckoutService`.

## Guardrails

- Do not rebuild/deploy the full `server2` dirty worktree until it is split and each group has validation.
- Keep `/webhooks/payments/mercadopago/` as canonical production notification URL for now.
- Keep `/webhooks/v1/mercadopago/` as fixed compatibility path; do not remove without telemetry.
- Do not remove duplicate chat/WebSocket clients in `pastita-dash` until a shared adapter is built and verified.

## Update — 2026-04-30

- P0 migration drift closed for `agents`:
  - Added `apps/agents/migrations/0007_alter_agent_base_url_alter_agent_model_name_and_more.py`.
  - `python manage.py makemigrations --check --dry-run` now reports `No changes detected`.
- P1 smoke contracts added:
  - `apps/stores/tests/test_smoke_contracts.py`.
  - Covers `GET /api/v1/stores/{slug}/catalog/`, `GET /api/v1/public/{slug}/catalog/`, guest `POST /api/v1/stores/{slug}/checkout/`, `GET /api/v1/stores/orders/by-token/{token}/`, `GET /api/v1/stores/customer/orders/{id}/?token=...`, and `POST /api/v1/stores/{slug}/delivery-fee/` with explicit `distance_km`.
- `pastita-dash` P0 contract alignment:
  - `src/services/intents.ts` now uses `/whatsapp/automation/dashboard/stats/` and `/whatsapp/automation/settings/`, matching `server2`.
  - `src/pages/automation/IntentStatsPage.tsx` supports backend `top_intents[].intent_type`.
  - `src/services/whatsapp.ts` now calls real `rotate_token` and `business_profile` endpoints.
- Validation:
  - `server2`: `python manage.py check`.
  - `server2`: `python manage.py test apps.stores.tests.test_smoke_contracts apps.automation.tests.test_pipeline --keepdb -v 2` passed, 42 tests.
  - `pastita-dash`: `npm run build` passed.

## Update — 2026-04-30 Continued

- `pastita-dash` pagination hardening:
  - Added `normalizePaginatedEnvelope()` in `src/services/api.ts`.
  - Updated `orders.ts`, `conversations.ts`, and `payments.ts` to accept both DRF paginated envelopes and direct arrays.
- `pastita-dash` reports tabs:
  - `AnalyticsPage` no longer renders the same overview for `Faturamento`, `Produtos`, and `Clientes`.
  - Added real tab-specific renderers using the existing reports API data.
- `server2` automation flow POC:
  - Fixed `apps/automation/api/views/flow_views.py` missing `Q` import for non-superuser queryset filters.
- Validation:
  - `pastita-dash`: `npm run build` passed.
  - `server2`: `python manage.py check` passed.
  - `server2`: `python manage.py test apps.stores.tests.test_smoke_contracts apps.automation.tests.test_pipeline --keepdb -v 2` passed, 42 tests.

## Update — 2026-04-30 P2 WhatsApp CheckoutService

- P2 order unification started safely after contract tests:
  - `WhatsAppOrderService.create_order_from_cart()` now routes simple WhatsApp product carts through `CheckoutService.create_order()`.
  - It builds a transient `StoreCart`, keeps WhatsApp payment inline, updates `CustomerSession`, and broadcasts `order.created` as before.
  - Legacy direct order creation remains as fallback for WhatsApp catalog price overrides, which `StoreCartItem` cannot represent yet.
- `CheckoutService` now supports:
  - `delivery_data.pre_calculated_fee` / `delivery_fee_override` for pre-quoted WhatsApp delivery fees.
  - `delivery_data.metadata`, including `metadata.source = "whatsapp"`.
  - Email automation suppression for WhatsApp orders and `@whatsapp.bot` customer emails.
- Added WhatsApp/storefront equivalence tests in `tests/test_whatsapp_order_service.py` for pickup and default delivery order shape.
- Validation:
  - `server2`: `python manage.py test tests.test_whatsapp_order_service --keepdb -v 2` passed, 16 tests.
  - `server2`: `python manage.py test tests.test_whatsapp_order_service tests.test_checkout_service apps.stores.tests.test_smoke_contracts apps.automation.tests.test_pipeline --keepdb -v 2` passed, 80 tests.
  - `server2`: `python manage.py check` passed.
  - `server2`: `python manage.py makemigrations --check --dry-run` reported no changes.
  - `server2`: `python -m py_compile apps/whatsapp/services/order_service.py apps/stores/services/checkout_service.py` passed.
