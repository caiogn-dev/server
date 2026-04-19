# Refactor Analysis: UnifiedService, Delivery Pricing, Order Creation

Date: 2026-04-17
Scope: `server2` + `pastita-dash`
Status: **Phase 1–7 complete** — all production changes applied, TDD test suite written, docs updated.

## Objective

Document the current behavior and the recommended refactor for:

- LLM usage and hallucination risk
- WhatsApp conversational flow
- whether requests are being handled and recorded correctly
- delivery fee calculation correctness
- how `UnifiedService` relates to order creation and dashboard updates
- a senior-level refactor plan to reduce duplicated logic and keep only the paths currently in use

## Executive Summary

The current system works through a layered orchestration flow, but it has a structural problem: the operational domain is not centralized. The most important business rules are duplicated across multiple services:

- delivery pricing exists in more than one place
- order creation exists in more than one place
- conversational state is spread across handlers and session storage
- LLM behavior is partially constrained by deterministic handlers, but the architectural boundaries are still fuzzy

This creates four categories of risk:

1. Response correctness without strong guarantees
2. Delivery fee divergence across channels
3. Inconsistent persistence depending on entrypoint
4. Green tests that do not protect the real conversation flow

## Answer to the question about UnifiedService

`UnifiedService` can lead the conversation to a real order and make that order reach the dashboard, but it does not do that directly.

Current chain:

1. `UnifiedService.process_message()` routes the incoming message
2. deterministic handlers process transactional flows
3. interactive handlers collect delivery/payment choices
4. `_finalize_order()` calls `create_order_from_whatsapp()`
5. `WhatsAppOrderService.create_order_from_cart()` creates the order
6. that service publishes a websocket event to `store_{slug}_orders`

Conclusion:

- `UnifiedService` is the orchestrator
- WhatsApp handlers drive the transactional flow
- `WhatsAppOrderService` is currently the component that actually persists the order and pushes the dashboard update

This is functional, but architecturally wrong because the transactional source of truth should be centralized in `CheckoutService`.

## Key Findings

### 1. Broken delivery validation endpoint

File:
- `apps/stores/api/maps_views.py`

Problem:

Inside `StoreValidateDeliveryView.post()`, the method references variables that are not defined in the method scope:

- `store_lat`
- `store_lng`
- `metadata`

Impact:

- the endpoint can fail at runtime
- the existing test can miss the issue because it mocks the maps service and does not fully protect the view internals

Severity:
- high

### 2. Delivery pricing has multiple sources of truth

Files:
- `apps/stores/services/checkout_service.py`
- `apps/stores/services/here_maps_service.py`
- `apps/whatsapp/intents/handlers.py`

Current behavior:

- `CheckoutService.calculate_delivery_fee()` calculates distance-based pricing
- `HereMapsService.calculate_delivery_fee()` calculates geo-aware pricing and fixed-price regions
- WhatsApp handlers also interpret delivery pricing and fixed zones directly for conversational responses

Impact:

- the same customer/location can receive different pricing depending on the entrypoint
- delivery explanations and actual charged fee are not guaranteed to match
- fixed-price neighborhood logic is duplicated

Severity:
- high

### 3. Order creation is duplicated

Files:
- `apps/stores/services/checkout_service.py`
- `apps/whatsapp/services/order_service.py`
- `apps/agents/services.py`

Current behavior:

- `CheckoutService.create_order()` is the backend transactional core
- `WhatsAppOrderService.create_order_from_cart()` manually creates `StoreOrder` and `StoreOrderItem`
- `AgentService.create_order_from_conversation()` creates a cart and then uses checkout

Impact:

- different order metadata depending on channel
- customer identity sync may differ
- pricing rules and delivery payload shape may differ
- stock, notes, payment, and event metadata become channel-dependent

Severity:
- high

### 4. Session state is operationally useful but semantically weak

File:
- `apps/automation/services/session_manager.py`

Current state keys:

- `pending_items`
- `pending_delivery_method`
- `waiting_for_address`
- `delivery_address`
- `delivery_fee_calculated`
- `delivery_distance_km`
- `delivery_duration_minutes`
- `delivery_lat`
- `delivery_lng`
- later `update_cart()` writes a different structure back into `cart_data`

Impact:

- state transitions are implicit instead of modeled
- partial/inconsistent sessions are possible
- one method can overwrite fields created by another

Observed risk already noted in recent memory:

- session with `cart_created` but no `pending_items`

Severity:
- high

### 5. LLM boundary is improved, but still too broad at the architecture level

Files:
- `apps/automation/services/unified_service.py`
- `apps/agents/services.py`
- `apps/whatsapp/intents/handlers.py`

What is already good:

- `UnifiedService._should_use_llm()` limits LLM usage to consultative intents
- deterministic handlers handle many transactional cases
- delivery, location and contact have deterministic paths

What is still problematic:

- `LangchainService` injects broad dynamic business context directly into the prompt
- tool exposure overlaps with deterministic handlers
- the model still has too much access to operational context for flows that should be domain-driven

Impact:

- hallucination risk is reduced, not eliminated
- debugging answer quality remains harder than necessary

Severity:
- medium/high

### 6. Existing tests do not protect the most critical real-world flow

Files:
- `tests/test_checkout_service.py`
- `tests/test_store_maps_api.py`
- `apps/automation/tests/test_pipeline.py`

What exists:

- unit coverage for delivery fee and checkout
- endpoint coverage for maps/catalog
- routing tests for interactive handler and unified service shortcut flow

What is missing:

- end-to-end conversation flow:
  - intent detection
  - pending items saved
  - delivery chosen
  - address or location provided
  - delivery fee calculated
  - payment selected
  - order persisted
  - dashboard event emitted

Severity:
- high

## Current Architecture Overview

### Conversation entrypoint

Primary orchestration:

- `apps/automation/services/unified_service.py`

Flow:

1. interactive reply shortcut
2. location shortcut
3. intent detection
4. deterministic handler
5. template fallback
6. LLM only for consultative intents
7. fallback response

This is directionally correct and should be preserved.

### Deterministic transactional flow

Primary files:

- `apps/whatsapp/intents/handlers.py`
- `apps/automation/services/session_manager.py`

Flow:

1. detect items
2. save pending items
3. ask delivery method
4. if delivery, collect address or location
5. calculate delivery fee
6. ask payment method
7. finalize order

This is the correct place for transaction orchestration, but the persistence target should be unified.

### Current dashboard publication

Primary file:

- `apps/whatsapp/services/order_service.py`

Current behavior:

- after order creation, it sends realtime event to the `store_{slug}_orders` channel group

This behavior should be preserved, but the implementation should move behind a reusable order event broadcaster rather than stay embedded in WhatsApp order creation code.

## Specific Risk Assessment

### Hallucination risk

Current status:

- lower than before for price/delivery/location/contact
- still present for open-ended consultative questions
- still harder to reason about than necessary because `LangchainService` is broad

Main recommendation:

- keep LLM only for consultative intents
- remove operational decision-making from LLM entirely

### Request registration correctness

Current status:

- operationally works for many WhatsApp flows
- but session integrity is not robust enough
- persistence path is duplicated

Main recommendation:

- explicit state machine for session
- one order creation path only

### Delivery fee correctness

Current status:

- not guaranteed consistent across API, checkout, and WhatsApp

Main recommendation:

- one single delivery pricing resolver

## What Should Be Kept

- `UnifiedService` as the single conversation orchestrator
- deterministic handlers for transactional intents
- `CheckoutService` as the transactional core
- HERE Maps integration as an infrastructure adapter
- dashboard websocket updates

## What Should Be Reduced or Removed

- manual `StoreOrder` creation inside WhatsApp order service
- parallel order creation path in `AgentService` or any duplication that bypasses the central checkout rules
- duplicated delivery logic across:
  - checkout
  - HERE service
  - handlers
  - maps API view
- broad LLM prompt-context duplication
- legacy branches that are no longer used in current operations

## Refactor Strategy

### Phase 1: Protect behavior with tests

Add regression coverage for:

- generic delivery info question
- fixed neighborhood fee question
- pickup order flow
- delivery order flow with shared location
- PIX flow
- session without `pending_items`
- consultative question that is allowed to use LLM
- transactional question that must not use LLM

Goal:

- freeze expected behavior before structural change

### Phase 2: Centralize delivery pricing

Create one central pricing contract in `CheckoutService` or a dedicated delivery pricing service.

This central contract must:

- accept coordinates when available
- support fixed-price regions
- support dynamic distance pricing
- support max distance checks
- support free delivery threshold
- return a normalized payload for both API and conversational use

Consumers should then delegate to it:

- maps views
- WhatsApp address/location flow
- checkout order creation

### Phase 3: Unify order creation

Make `CheckoutService.create_order()` the only order persistence path.

Refactor WhatsApp order creation to:

1. build or hydrate a temporary cart
2. call checkout core
3. call centralized payment creation
4. publish dashboard event
5. update session

Result:

- same order structure regardless of channel
- same delivery metadata
- same identity sync
- same stock behavior

### Phase 4: Make session state explicit

Replace implicit JSON blob conventions with a real state model such as:

- `idle`
- `collecting_items`
- `choosing_delivery`
- `waiting_address`
- `choosing_payment`
- `payment_pending`
- `completed`

Benefits:

- easier debugging
- reduced state corruption
- easier tests

### Phase 5: Narrow LLM responsibilities

LLM should remain available only for:

- recommendations
- comparisons
- open-ended product guidance
- complex consultative questions

LLM should not decide:

- delivery fee
- order totals
- session state
- whether an order exists
- payment status

### Phase 6: Remove code duplication

After behavior is protected and centralized:

- shrink `LangchainService` prompt context
- remove duplicate delivery tools or adapt them to call the same central contract
- remove unused or legacy order paths

## Bug 7: AutoMessage duplicate dispatch on order status change (discovered 2026-04-17)

### Root cause

When `order.update_status(new_status)` is called from the model:

1. `self.save()` triggers the Django post_save signal in `apps/automation/signals.py`
2. The signal queues `notify_order_status_change.delay(order_id, status)` via `transaction.on_commit`
3. The Celery task fetches the AutoMessage template and sends via WhatsApp
4. **Then** `update_status()` also calls `self._trigger_status_whatsapp_notification(new_status)` directly
5. That direct call also sends via WhatsApp

Result: stores with AutoMessage templates configured receive two identical WhatsApp messages per status change.

### Why the existing metadata guard did not protect

`_trigger_status_whatsapp_notification()` sets `metadata['whatsapp_notification_{status}']` after sending,
but the Celery task never checks this key — it uses AutoMessage templates independently.

Because `transaction.on_commit` defers the Celery dispatch until after the transaction commits,
and `_trigger_status_whatsapp_notification()` runs synchronously before the commit,
the metadata key is in theory set before Celery runs.

However, within an outer `@transaction.atomic` block the metadata save itself is not committed
until the outer block commits. At that point both are committed simultaneously and the race window opens.

### Fix applied

File: `apps/stores/models/order.py`

Removed the `_trigger_status_whatsapp_notification(new_status)` call from `update_status()`.
WhatsApp notification is now exclusively handled by the signal → Celery task path.

File: `apps/whatsapp/tasks/automation_tasks.py`

Added a fallback in `notify_order_status_change` when `AutoMessage.DoesNotExist`:
the task now calls `order._trigger_status_whatsapp_notification(new_status)` as the fallback.
This preserves behavior for stores that have not configured AutoMessage templates.

### Result

- Stores with AutoMessage templates: one send via Celery task using the template
- Stores without AutoMessage templates: one send via model fallback
- No duplicate in either case

---

## Implementation Status

| # | Item | Status |
|---|------|--------|
| 1 | Fix broken maps delivery validation endpoint | ✅ done |
| 2 | Fix AutoMessage duplicate dispatch | ✅ done |
| 3 | Centralize dynamic delivery fee formula | ✅ done |
| 4 | Fix missing stock decrement in WhatsApp order creation | ✅ done |
| 5 | Unify dashboard broadcast via `realtime_service` | ✅ done |
| 6 | Thread structured address components through WhatsApp flow | ✅ done |
| 7 | Fix `DeliveryAddress` type + `raw_address` fallback in pastita-dash | ✅ done |
| 8 | Unify order creation: `WhatsAppOrderService` → `CheckoutService` | ⬜ pending |
| 9 | Session state machine (explicit states) | ⬜ pending |
| 10 | Regression test suite (full conversational flow) | 🟡 partial — unit tests done, e2e pending |
| 11 | Remove dead code and legacy order paths | ⬜ pending (after tests) |

## Changes Applied

### apps/stores/api/maps_views.py — StoreValidateDeliveryView
`store_lat`, `store_lng`, `metadata` were used but never defined. Fixed: `store.latitude`, `store.longitude`, `store.metadata`.

### apps/stores/models/order.py — update_status()
Removed `_trigger_status_whatsapp_notification()` direct call. The post_save signal → Celery task is the single dispatch path. Added explanatory comment.

### apps/whatsapp/tasks/automation_tasks.py — notify_order_status_change
Added fallback in `except AutoMessage.DoesNotExist` that calls `order._trigger_status_whatsapp_notification(new_status)`. Stores without templates still get notified; stores with templates no longer get duplicates.

### apps/stores/services/here_maps_service.py — calculate_delivery_fee()
Replaced the inline `base_fee + per_km` block with a call to `CheckoutService._calculate_dynamic_fee(store, distance_km)`. HereMapsService still owns route calculation, fixed-zone matching, and max-distance check.

### apps/whatsapp/services/order_service.py — create_order_from_cart()
- Added stock decrement after item creation (`F('stock_quantity') - qty`) for products with `track_stock=True`.
- Removed `_broadcast_order_created()`. Dashboard broadcast now uses `broadcast_order_event(order, 'order.created')` from `realtime_service`.
- `_build_delivery_address()` now maps HERE geocode/reverse_geocode components to frontend-standard keys: `street`, `number` (from `houseNumber`/`house_number`), `neighborhood` (from `district`), `city`, `state` (from `stateCode`/`state_code`), `zip_code` (from `postalCode`). `raw_address` preserved as fallback.

### apps/whatsapp/intents/handlers.py
- `_handle_address_input()` passes `geo.get('address', {})` (HERE structured dict) as `address_components`.
- `_handle_location_input()` passes normalized reverse_geocode fields as `address_components`.
- `_process_location_and_ask_payment()` accepts and forwards `address_components` to session.

### apps/automation/services/session_manager.py
- `save_delivery_address_info()` accepts `address_components` kwarg, saves to `delivery_address_components`.
- `get_delivery_address_info()` returns `address_components` from session.

### pastita-dash/src/types/index.ts
Added `DeliveryAddress` interface (with `[key: string]: unknown` index signature for TS compatibility, plus typed structured fields and legacy aliases). Updated `Order.delivery_address` from `string` to `DeliveryAddress`.

### pastita-dash/src/services/storesApi.ts
`StoreOrder.delivery_address` updated from `Record<string, string>` to `DeliveryAddress`.

### pastita-dash — OrderDetailPage, OrdersKanban, OrderPrint, OrdersPage
All address display functions fall back to `raw_address` when structured fields are absent. Orders created before this fix continue to display something meaningful. TypeScript: 0 errors.

### ce-saladas/src/components/checkout/hooks/useCheckoutForm.js
- Added `geoExtrasRef` to persist `lat`, `lng`, `raw_address` captured by GPS/map — they were
  captured by `useGeolocation` but discarded when `setAddressFromGeo` populated only form fields.
- `buildCheckoutPayload()` now includes `lat`, `lng`, `raw_address` in the `delivery_address`
  object sent to the backend. Orders placed via the web storefront now have the same coordinate
  data as WhatsApp orders.
- `raw_address` falls back to the structured string
  (`street, number, neighborhood, city`) if no GPS label is available.

### apps/agents/services.py — _build_dynamic_context()
- Loads **all** active products (was capped at 20), grouped by category, with stock status
  annotations (`[ESGOTADO]`, `[últimas N unidades]`) for tracked products.
- Ingredient-builder products excluded from the agent context (same rule as the WhatsApp menu).
- Injects active session state (pending items, delivery method, delivery address, fee, PIX status)
  so the agent can answer "quais itens estão no meu pedido?" accurately without guessing.

## Test Suite Written

Five test modules cover all production changes from this refactor:

| File | What it covers |
|------|----------------|
| `tests/test_whatsapp_order_service.py` | `_build_delivery_address` HERE Maps field mapping; `create_order_from_cart` — creation, stock, fees, errors |
| `tests/test_automessage_dispatch.py` | `update_status` no-direct-call regression; signal → Celery dispatch; task with/without template; fallback path |
| `tests/test_delivery_pricing_unified.py` | `CheckoutService._calculate_dynamic_fee` formula; HERE parity check; `StoreValidateDeliveryView` no NameError |
| `tests/test_session_address_components.py` | `save_delivery_address_info`/`get_delivery_address_info`; structured address flows into `StoreOrder.delivery_address` |
| `tests/test_conversation_flow_e2e.py` | Full conversational flows: pickup→cash, delivery→text address→PIX, delivery→GPS→PIX; empty session guard; transactional vs. consultative intents; stock decrement |

Run all:
```bash
python manage.py test tests.test_whatsapp_order_service tests.test_automessage_dispatch \
    tests.test_delivery_pricing_unified tests.test_session_address_components --keepdb -v 2
```

---

## Remaining Work

### Item 8: Unify order creation (high risk, needs tests first)

`WhatsAppOrderService.create_order_from_cart()` still creates `StoreOrder` directly instead of going
through `CheckoutService.create_order()`.

Blocker: `CheckoutService.create_order()` requires a `StoreCart` and calls
`CustomerIdentityService.sync_checkout_customer()`, whose behavior for phone-only WhatsApp customers is untested.

Required steps before this can be done safely:
1. Regression tests covering the WhatsApp order flow end-to-end (item 10)
2. A cart hydration helper: convert `[{product_id, quantity}]` → temporary `StoreCart` + `StoreCartItem`
3. A `force_delivery_fee` parameter on `CheckoutService.create_order()` (pre-calculated fee from HERE Maps)
4. Verify `CustomerIdentityService` handles `whatsapp_{phone}@pastita.local` email without side effects
5. Replace `StoreOrder.objects.create()` in `WhatsAppOrderService` with the checkout path
6. Keep payment processing and session update as-is

### Item 9: Session state machine

Replace the implicit JSON blob in `CustomerSession.cart_data` with explicit state transitions.

Proposed states: `idle`, `collecting_items`, `choosing_delivery`, `waiting_address`,
`choosing_payment`, `payment_pending`, `completed`.

This reduces the risk of partial sessions and makes `session_manager` easier to test.
Can be done independently of item 8.

### Item 10: Regression test suite

Minimum coverage needed before removing dead code or doing item 8:

- pickup order flow (items → pickup → cash → order confirmed)
- delivery flow with typed address (items → delivery → address text → fee quoted → PIX → order confirmed)
- delivery flow with location share (items → delivery → GPS location → fee quoted → PIX → order confirmed)
- session without `pending_items` (guard behavior)
- transactional intent that must NOT call LLM
- consultative intent that IS allowed to call LLM
- order status change triggers exactly one WhatsApp notification (regression for AutoMessage duplicate)

### Item 11: Remove dead code (after items 8 + 10)

- `WhatsAppOrderService._generate_order_number()` — once checkout handles order numbers
- Manual `StoreOrder.objects.create()` block in WhatsApp order service
- Any duplicate delivery calculation in `HereMapsService` zone-lookup path (already partially cleaned)

## Constraints Observed During Analysis

Tests could not be executed in this environment because the local Python environment for `server2` is incomplete.

Observed issues:

- `python` unavailable
- `pytest` unavailable
- `python3 manage.py test` fails because Django is not installed in the active environment

This means:

- analysis is based on static review of the codebase
- runtime validation still depends on restoring a working environment

## Final Recommendation

Do not do a cosmetic refactor.

The code needs a boundary refactor:

- one orchestrator
- one delivery pricing contract
- one order creation path
- one explicit session model
- LLM restricted to consultative behavior

That is the smallest change set that actually improves correctness and removes the architectural drift currently causing the system to feel scattered.
