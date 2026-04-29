# Implementation Priority Roadmap — Server2 + Pastita Dash + Storefronts

Scope: `server2`, `pastita-dash`, `ce-saladas`, `pastita-3d`, and customer/mobile clients that consume the same catalog, cart, checkout, order, delivery and WhatsApp contracts.

## Method

Every priority must follow this loop:

1. Inventory current consumers.
2. Write or update a contract test.
3. Implement the smallest canonical path.
4. Keep compatibility paths as delegators.
5. Add telemetry to compatibility paths.
6. Remove legacy only after observed non-use and passing contract tests.

Do not start broad cleanup while `server2` has mixed uncommitted production changes. Split work by domain first.

## P0 — Stabilize The Working Base

### 1. Production vs Git inventory

Owner: `pastita-platform-orchestrator`

Actions:

- Compare running `pastita_web` container files with Git HEAD for changed hotfix areas.
- Split `server2` dirty worktree into commits by domain:
  - checkout/order
  - WhatsApp/chat/media
  - delivery/geo
  - Meta CAPI
  - printing
  - docs/tests
- Decide whether untracked migrations for conversations and printing are part of the next deploy.

Acceptance:

- `git status` has only intentional changes.
- Every deployable change has a commit and rollback note.

### 2. Frontend contract matrix

Owner: `pastita-frontend-contracts`

Actions:

- Map endpoints used by:
  - `ce-saladas`
  - `pastita-3d`
  - `pastita-dash`
  - `ce-saladas-flutter`
- Mark each endpoint:
  - `canonical`
  - `compat`
  - `dead-candidate`

Acceptance:

- Checkout, cart, catalog, delivery quote, order status, WhatsApp messages, conversations and campaigns are mapped.
- No route removal starts before this matrix exists.

## P1 — Catalog/Cardapio Contract

Owner: `server2-backend-general` + `pastita-frontend-contracts`

Problem:

`ce-saladas` and `pastita-3d` display similar storefront/catalog data with duplicated frontend shaping. Dashboard edits products/categories through a separate operational surface.

Implementation:

- Define one storefront catalog response shape for:
  - store
  - categories
  - products
  - combos
  - product type/category slug
  - image URL
  - stock state
  - price/original price
  - tags/metadata
  - availability
- Ensure `pastita-dash` edits exactly the fields the storefronts display.
- Add contract tests on `server2` for `/api/v1/stores/{slug}/catalog/`.
- Add frontend presentation helpers with unit tests for category grouping and display order.

Acceptance:

- `pastita-3d` and `ce-saladas` can render from the same canonical fields.
- Mobile cardapio can group by current database categories such as `Molhos` and `Rondellis`.
- No frontend has to infer critical category behavior from display text only.

## P2 — Cart And Checkout Canonicalization

Owner: `server2-backend-general` + `server2-database-models`

Problem:

Order creation and cart identity are split across site and WhatsApp flows, with race risks in cart/order models.

Implementation:

- Make `CheckoutService` the canonical `StoreOrder` factory.
- Make WhatsApp order flow build an internal checkout payload and call the same service.
- Add DB constraints:
  - one active cart per `(store, user)`
  - one active cart per `(store, session_key)`
  - stable cart line identity for product/variant/options
- Add retry or deterministic strategy for `order_number`.
- Add checkout regression tests for:
  - product order
  - combo/custom item order
  - guest cart
  - authenticated cart
  - Pix payload
  - realtime order event

Acceptance:

- Storefront and WhatsApp produce the same order totals for the same payload.
- Checkout tests cover both `ce-saladas` and `pastita-3d` store slugs.

## P3 — Delivery/Geo Centralization

Owner: `server2-backend-general`

Problem:

Delivery fee and map behavior still exist in old HERE frontend paths and backend GeoService paths.

Implementation:

- Backend owns:
  - geocode
  - reverse geocode
  - route
  - delivery quote
  - fixed-zone handling
  - out-of-area reason
- Frontends only send address/lat/lng and render result.
- Keep HERE compatibility as alias only, with usage logging.
- Add tests for known Palmas examples and fixed zones.

Acceptance:

- `ce-saladas`, `pastita-3d`, WhatsApp and Flutter all get delivery fee from backend.
- No frontend calculates final delivery price.

## P4 — Pastita Dash Operational Cleanup

Owner: `pastita-frontend-contracts`

Implementation:

- Create a single chat feature:
  - `features/chat/api`
  - `features/chat/realtime`
  - `ConversationList`
  - `ConversationPanel`
  - `MessageComposer`
- Replace duplicated WebSocket clients with one backend-aligned client.
- Create `api.postForm()` / `api.patchForm()` for all multipart uploads.
- Remove fake-success mocks for backend-missing WhatsApp capabilities.

Acceptance:

- Uploads no longer set manual `Content-Type`.
- WhatsApp inbox and reusable chat window consume the same message adapter.
- Unsupported backend features are explicit in UI, not mocked as success.

## P5 — Webhooks And Automation

Owner: `server2-backend-general` + `server2-database-models`

Implementation:

- Fix Mercado Pago central route by delegating to the real store payment handler or extracting one service.
- Add unique DB idempotency for webhooks.
- Convert old automation tasks into wrappers around `UnifiedService` or no-op telemetry.
- Choose one campaign send path and make legacy task names delegators.

Acceptance:

- Payment/webhook duplicate requests are handled by DB-backed idempotency.
- Legacy tasks cannot emit old Pix or old LLM responses.

## P6 — Code Removal With Telemetry

Owner: `pastita-platform-orchestrator`

Candidates:

- `apps/whatsapp/services/automation_service.py`
- `apps/automation/tasks/unified_messaging_tasks.py`
- old HERE frontend/service paths
- flat duplicate store routes
- dashboard fake-success WhatsApp APIs

Acceptance:

- Compatibility path logs zero usage across agreed observation window.
- Canonical path has tests.
- Removal PR lists old caller inventory.

## Current Pastita-3D Mobile Cardapio Change

Implemented direction:

- Category presentation helper with tests.
- Grouped catalog sections for unfiltered view.
- Mobile grid changed from one-card-per-row to compact 2-column cards.
- Product card mobile layout hides long descriptions and weight badges to reduce scroll.

Validation:

- `npm test`
- `npm run build`

Known local validation blocker:

- Browser validation against local API is currently blocked by CORS on `http://127.0.0.1/api/v1` from the Next dev origin. Direct `curl` to catalog/cart succeeds through nginx. For full Playwright/Chrome validation, either run frontend through the same origin/proxy or allow the dev origin in backend CORS.
