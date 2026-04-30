# P2 — WhatsApp Order Creation via CheckoutService

## Current WhatsApp Order Flow

`WhatsAppOrderService.create_order_from_cart()` in `apps/whatsapp/services/order_service.py`:

1. Receives `items` (list of `{product_id, quantity}`), `delivery_method`, `payment_method`, optional `delivery_fee_override` and `addr_info` from the calling handler.
2. Validates each product via `StoreProduct.objects.get(id=..., store=self.store, is_active=True)` — skips invalid products silently.
3. Supports an optional `price_source == 'whatsapp_catalog'` override on the unit price.
4. Calculates delivery fee:
   - `pickup` → R$ 0
   - `delivery_fee_override` present → uses that value directly (from HERE Maps geocoding result)
   - otherwise → falls back to `store.default_delivery_fee`, respecting `store.free_delivery_threshold`
5. Creates `StoreOrder` directly via `StoreOrder.objects.create(...)` with `source = 'whatsapp'` in `metadata`. Does NOT go through `CheckoutService.create_order()`.
6. Creates `StoreOrderItem` rows and atomically decrements stock with `F('stock_quantity') - quantity`.
7. Processes payment inline:
   - `pix` → `CheckoutService.create_payment(order, 'pix')`
   - `card` → `CheckoutService.create_payment(order, 'credit_card')`
   - `cash` → `CheckoutService.create_payment(order, 'cash')`
8. Broadcasts `order.created` WebSocket event via `broadcast_order_event()` (on commit).
9. Updates `CustomerSession` with PIX state via `get_session_manager()`.
10. `customer_email` is hardcoded as `whatsapp_{phone}@whatsapp.bot` — not a real address.
11. No coupon validation, no loyalty reward, no combo item support, no variant support.
12. `order_number` is generated locally (`{PREFIX}-{timestamp}-{uuid4[:4]}`), not via a store-level sequence.
13. No `CustomerIdentityService.sync_checkout_customer()` call — customer FK on the order is always `None`.

Triggered by: `apps/whatsapp/intents/handlers.py` (checkout step handlers) → `create_order_from_whatsapp()` wrapper.

---

## Current CheckoutService Flow

`CheckoutService.create_order(cart, customer_data, delivery_data, coupon_code, notes, use_loyalty_reward)` in `apps/stores/services/checkout_service.py`:

1. Receives a fully-populated `StoreCart` with items already added.
2. Runs `cart_service.validate_stock_for_checkout(cart)` — raises on stock errors.
3. Sanitizes delivery address coordinates (detects conflicting quadra numbers, strips stale geocode).
4. Calculates delivery fee via `CheckoutService.calculate_delivery_fee(store, distance_km, zip_code)` → `normalize_delivery_quote()`. Raises if address is out of delivery zone.
5. Syncs/creates the customer record via `CustomerIdentityService.sync_checkout_customer()` — links `StoreCustomer` and `UnifiedUser` to the order.
6. Validates and applies a coupon (`StoreCoupon`) atomically, incrementing usage.
7. Supports loyalty reward (Clube Verde free salad discount).
8. Creates `StoreOrder` with full `customer` FK, `discount`, `coupon_code`, `tax`, and rich `metadata` (delivery zone, delivery quote, estimated_minutes, loyalty, customer ids, cpf).
9. Creates `StoreOrderItem` rows including variants (with `variant_name`, `sku`) and combo items (virtual and real, with combo stock decrement).
10. Clears and deactivates the cart.
11. Triggers `order_received` email automation.
12. Does NOT call `create_payment` — payment is triggered separately by the frontend after receiving the order.

---

## Gaps — What Would Need to Change

| # | Gap | Direction |
|---|-----|-----------|
| 1 | **No StoreCart** | WhatsApp builds items from conversation — there is no `StoreCart` object. Need to either create a transient cart or refactor `create_order` to accept items directly. |
| 2 | **Customer identity** | WhatsApp uses `whatsapp_{phone}@whatsapp.bot` as email; no `CustomerIdentityService` call; `order.customer` FK is `None`. `CheckoutService` links a real `UnifiedUser` and `StoreCustomer`. |
| 3 | **Delivery fee calculation** | WhatsApp uses HERE-override or `store.default_delivery_fee` flat. `CheckoutService` uses zone-based `calculate_delivery_fee()` with `normalize_delivery_quote()` and can reject out-of-zone addresses. |
| 4 | **Coupon/loyalty support** | WhatsApp has none. `CheckoutService` supports both. |
| 5 | **Variant support** | WhatsApp ignores variants. `CheckoutService` handles `StoreProductVariant` with separate stock decrements. |
| 6 | **Combo item support** | WhatsApp has no combo items. `CheckoutService` handles real and virtual combos. |
| 7 | **Payment is inline** | `WhatsAppOrderService` calls `CheckoutService.create_payment()` immediately inside the order creation transaction. `CheckoutService.create_order()` leaves payment for a separate step. Routing through `create_order` would require explicitly calling `create_payment` afterwards. |
| 8 | **Order number generation** | WhatsApp generates its own `{PREFIX}-{timestamp}-{uuid}` string. `CheckoutService` lets the DB/model generate `order_number`. |
| 9 | **Email automation** | `CheckoutService.create_order()` always fires `trigger_order_email_automation(order, 'order_received')`. WhatsApp path does not. WhatsApp customer emails are `@whatsapp.bot` — email automations would silently fail anyway. |
| 10 | **source metadata** | WhatsApp sets `metadata.source = 'whatsapp'`. `CheckoutService` does not set a `source` field — it must be added to `metadata` post-creation or via a parameter. |
| 11 | **Stock validation** | WhatsApp silently skips invalid products. `CheckoutService` validates all stock up front and raises. |

---

## Minimum Implementation Plan

Steps in dependency order:

1. **Add `create_cart_from_items()` helper** in `WhatsAppOrderService` (or a new `WhatsAppCartBuilder`): given `[(product_id, quantity)]` + `store`, create a transient `StoreCart` attached to a guest user (or the resolved `UnifiedUser`). This is the main prerequisite for plugging into `CheckoutService.create_order()`.

2. **Resolve customer identity before cart creation**: call `CustomerIdentityService.sync_checkout_customer()` with the phone number and optional name extracted from the conversation. Use the returned `user` as `cart.user`. This lets `create_order` attach the `customer` FK correctly.

3. **Build `delivery_data` dict** compatible with `CheckoutService`: map `delivery_method`, `delivery_fee_override` → `distance_km` (reverse-map if possible) or pass as a pre-calculated zone override. Add a `pre_calculated_fee` path in `normalize_delivery_quote()` or add an `addr_info` parameter to `create_order` for this case.

4. **Call `CheckoutService.create_order(cart, customer_data, delivery_data)`** instead of the direct `StoreOrder.objects.create()` block in `WhatsAppOrderService.create_order_from_cart()`.

5. **Inject WhatsApp metadata** post-creation: after `create_order` returns the order, patch `order.metadata['source'] = 'whatsapp'` and save with `update_fields`.

6. **Call `CheckoutService.create_payment(order, payment_method)`** immediately after (same behaviour as today — payment is inline for WhatsApp).

7. **Suppress email automation for WhatsApp orders** (or guard with `metadata.source`): add a guard in `trigger_order_email_automation` to skip when `order.metadata.get('source') == 'whatsapp'` and no real email is present.

8. **Update `_update_session()`** to work with the order returned by `CheckoutService.create_order()` — no change needed if the signature stays the same.

9. **Regression tests**: see Risk Assessment below.

---

## Risk Assessment

### What can break

| Risk | Severity | Notes |
|------|----------|-------|
| Out-of-zone rejection | High | `CheckoutService.calculate_delivery_fee` raises when address is outside all delivery zones. WhatsApp orders today never raise — they always compute a fee. Must add a fallback or a bypass flag for pre-calculated fees. |
| Stock validation raising mid-conversation | Medium | If a product is sold out between "add to cart" and "confirm order", `CheckoutService` will raise. WhatsApp today skips the product silently. Need to decide: raise and ask the user to revise, or skip silently. |
| Customer identity side-effects | Medium | `CustomerIdentityService.sync_checkout_customer()` creates/updates `UnifiedUser` and `StoreCustomer`. WhatsApp orders with `@whatsapp.bot` email currently produce no real user. This change will create real user records — needs a review of downstream effects (loyalty counts, marketing opt-in). |
| Email automation firing for WhatsApp | Low | `trigger_order_email_automation()` will fire with a `@whatsapp.bot` email — it will silently fail, but adds unnecessary DB writes and log noise. Add a source guard. |
| Order number format change | Low | Removing the custom `{PREFIX}-{timestamp}-{uuid}` format will change how order numbers look to existing users. Consider keeping the custom format via a `order_number` parameter on `create_order`. |
| Combo/variant items exposed | Low | WhatsApp currently doesn't add combos or variants. Once the cart goes through `CheckoutService`, it will attempt to handle them — safe as long as the cart builder never adds them. |

### Tests needed before implementing

1. `test_whatsapp_order_via_checkout_service_pix` — full happy path (delivery + PIX).
2. `test_whatsapp_order_via_checkout_service_pickup` — pickup + cash payment.
3. `test_whatsapp_order_out_of_zone_rejected` — verify the error is surfaced to the user gracefully.
4. `test_whatsapp_order_stock_validation_error` — product out-of-stock mid-checkout.
5. `test_whatsapp_customer_identity_created` — verify `UnifiedUser`/`StoreCustomer` are created.
6. `test_whatsapp_email_automation_suppressed` — `trigger_order_email_automation` NOT called for `@whatsapp.bot` email.
7. `test_whatsapp_order_metadata_source` — `order.metadata['source'] == 'whatsapp'` after creation.
8. Regression: existing storefront checkout tests must still pass (no changes to `CheckoutService` logic).
