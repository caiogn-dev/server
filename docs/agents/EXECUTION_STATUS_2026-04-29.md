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
3. Add contract tests before deeper refactors:
   - `/stores/{slug}/catalog/`
   - `/public/{slug}/catalog/`
   - Flutter checkout payload against `/stores/{slug}/checkout/`
   - delivery fee examples for Palmas fixed/dynamic zones
4. Only after contracts are in place, start P2: make WhatsApp order creation call `CheckoutService`.

## Guardrails

- Do not rebuild/deploy the full `server2` dirty worktree until it is split and each group has validation.
- Keep `/webhooks/payments/mercadopago/` as canonical production notification URL for now.
- Keep `/webhooks/v1/mercadopago/` as fixed compatibility path; do not remove without telemetry.
- Do not remove duplicate chat/WebSocket clients in `pastita-dash` until a shared adapter is built and verified.
