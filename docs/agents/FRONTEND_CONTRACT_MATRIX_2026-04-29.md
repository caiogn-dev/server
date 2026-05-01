# Frontend Contract Matrix — 2026-04-29

Scope: `ce-saladas`, `ce-saladas-flutter`, `pastita-dash`, and `server2` API contracts. This is the initial P1 matrix from `IMPLEMENTATION_PRIORITY_ROADMAP_2026-04-28.md`.

## Contract Status Legend

- `canonical`: preferred contract for new work.
- `compat`: supported because an active client still consumes it.
- `risk`: active consumer with mismatch, mock behavior, or duplicate ownership.
- `dead-candidate`: remove only after telemetry shows no use and a replacement test exists.

## Storefront Catalog

| Consumer | Endpoint | Status | Notes |
|---|---|---|---|
| `ce-saladas` web | `GET /api/v1/stores/{slug}/catalog/` | canonical | Main SSR/client catalog source in `pages/index.js`, `pages/cardapio.js`, and `src/services/storeApi.js`. Returns `store`, `categories`, `products`, `combos`, `featured_products`, `products_by_category`, `product_types`. |
| `ce-saladas-flutter` | `GET /api/v1/public/{slug}/catalog/` | risk | Mobile uses a different public catalog shape: `catalog` list. This should be either documented as mobile canonical or migrated to `/stores/{slug}/catalog/`. |
| `pastita-dash` | `GET /api/v1/stores/products/`, `GET /api/v1/stores/categories/` | canonical operational | Dashboard edits operational product/category records rather than storefront catalog. Contract must keep fields rendered by storefronts editable here. |

## Cart

| Consumer | Endpoint | Status | Notes |
|---|---|---|---|
| `ce-saladas` web | `GET /stores/{slug}/cart/`, `POST /cart/add/`, `PATCH/DELETE /cart/item/{id}/`, `DELETE /cart/clear/` | canonical storefront | Uses `X-Cart-Key` / `cart_key` guest identity. Supports product, combo, and virtual salad builder payload. |
| `ce-saladas-flutter` | `DELETE /stores/{slug}/cart/clear/`, `POST /stores/{slug}/cart/add/` before checkout | risk | Mobile keeps local cart then syncs by clearing/re-adding immediately before checkout. This can create race or partial-sync issues if cart endpoints diverge. |
| `pastita-dash` | none for customer cart | n/a | Dashboard creates manual orders directly through operational order API. |

## Checkout And Order Creation

| Consumer | Endpoint | Status | Notes |
|---|---|---|---|
| `ce-saladas` web | `POST /stores/{slug}/checkout/` | canonical storefront | Uses backend `CheckoutService`. Payload includes customer, delivery, payment, coupon/loyalty, Meta Pixel context. |
| `ce-saladas-flutter` | `POST /stores/{slug}/checkout/` | canonical target, risk payload | Uses same endpoint but builds payload separately after cart sync. Needs contract test against real mobile payload. |
| `pastita-dash` | `POST /stores/orders/` or `/stores/{slug}/orders/` | compat operational | Manual staff order creation uses `StoreOrderCreateSerializer`, not `CheckoutService`. It now accepts manual `discount`, `surcharge`, and `adjustment_reason`. Do not use for storefront checkout. |
| WhatsApp bot | internal order service / session manager | canonical target, fallback active | P2 started 2026-04-30: simple product carts now adapt into `CheckoutService.create_order()` through a transient `StoreCart`. Legacy direct order creation remains only for WhatsApp catalog price overrides until cart item price overrides are modeled. |

## Delivery And Geo

| Consumer | Endpoint | Status | Notes |
|---|---|---|---|
| `ce-saladas` web | `GET /stores/{slug}/delivery-fee/`, `POST /validate-delivery/`, `GET /route/`, global `GET /stores/maps/geocode/`, `GET /stores/maps/reverse-geocode/` | canonical backend geo | Frontend renders Google Maps and may call ViaCEP for CEP UX; backend owns geocode/reverse-geocode/route/final pricing. |
| `ce-saladas-flutter` | `POST /stores/{slug}/delivery-fee/`, `GET /stores/{slug}/route/` | canonical | Mobile gets fee from backend; route merge is frontend display only. |
| `pastita-dash` | `POST /stores/{slug}/delivery-fee/` in new order | canonical operational | Used for staff-created delivery orders. |

## Order Status And Receipts

| Consumer | Endpoint | Status | Notes |
|---|---|---|---|
| `ce-saladas` web | `GET /stores/orders/by-token/{access_token}/`, `GET /stores/orders/{id}/payment-status/`, `GET /stores/orders/{id}/whatsapp/` | canonical public | Used by payment success/error/pending pages and WhatsApp confirmation. |
| `ce-saladas-flutter` | `GET /stores/customer/orders/`, `GET /stores/customer/orders/{id}/`, `GET /stores/orders/by-token/{token}/`, `GET /stores/orders/{id}/payment-status/` | risk | Payment status path was fixed locally in `ce-saladas-flutter`; still needs versioning/owning-repo commit and device validation. |
| `pastita-dash` | `GET/PATCH/POST /stores/orders/`, `/stores/{slug}/orders/{id}/update_status/` | canonical operational | Staff order board/detail uses operational order APIs and websocket/SSE. |

## WhatsApp, Conversations, Campaigns

| Consumer | Endpoint | Status | Notes |
|---|---|---|---|
| `pastita-dash` | `/whatsapp/accounts/`, `/whatsapp/messages/*`, `/conversations/*`, `/campaigns/*`, `/ws/whatsapp/dashboard/` | mixed | Active dashboard surface. Mock-success methods were removed in commit `fad2bce`; remaining risk is duplicated chat clients (`WhatsAppWsContext`, `useWhatsAppWS`, reusable `ChatWindow`). |
| `ce-saladas` web | `/auth/whatsapp/send/`, `/auth/whatsapp/verify/`, `/auth/whatsapp/resend/` | canonical auth | WhatsApp OTP login/signup. |
| `ce-saladas-flutter` | `/auth/whatsapp/send/`, `/auth/whatsapp/verify/`, `/auth/whatsapp/resend/` | canonical auth | Same OTP endpoints as web. |

## Webhooks

| Endpoint | Status | Notes |
|---|---|---|
| `POST /webhooks/payments/mercadopago/` | canonical production | Checkout notification URL currently points here. Tested 2026-04-29 with safe payload: returns `{"status":"no_payment_id"}` and HTTP 200. |
| `POST /webhooks/v1/mercadopago/` | compat fixed | Central dispatcher was broken by missing import. Fixed in commit `124eccf`; hotfixed into `pastita_web` and `pastita_celery`. Safe synthetic events completed without `failed` status. |
| `POST/GET /webhooks/v1/whatsapp/` plus Meta no-slash compat | canonical/compat | Keep existing Meta compatibility paths. Do not remove until webhook app settings are inventoried. |

## Immediate Follow-Ups

1. Add one mobile checkout fixture test that posts the actual Flutter payload to `/stores/{slug}/checkout/`.
2. Version and validate the local `ce-saladas-flutter` payment status path fix in the owning repo.
3. Finish P2 fallback removal by modeling WhatsApp catalog price overrides or mapping those prices back to canonical product/variant pricing.
4. Expand `pastita-dash` P4 cleanup only after the shared chat/realtime adapter contract is written.

## Update — 2026-04-30

- Server contract tests now cover both catalog contracts:
  - `GET /api/v1/stores/{slug}/catalog/`
  - `GET /api/v1/public/{slug}/catalog/`
- Server smoke tests also cover guest checkout, by-token order read, customer order detail with token, and delivery-fee quote normalization.
- `pastita-dash` automation service now matches the real WhatsApp automation namespace:
  - `GET /api/v1/whatsapp/automation/dashboard/stats/`
  - `GET/PATCH /api/v1/whatsapp/automation/settings/`
- `pastita-dash` intent stats now accepts backend `top_intents[].intent_type`; old `intent` is kept as a compatibility alias in the type.
- `pastita-dash` WhatsApp account detail now uses real backend account actions for token rotation and business profile.

## Update — 2026-04-30 P2

- Added WhatsApp/storefront order-shape equivalence tests for pickup and delivery.
- WhatsApp simple product carts now use `CheckoutService.create_order()` internally.
- `CheckoutService` now accepts pre-calculated delivery fees and WhatsApp metadata, and suppresses email automation for WhatsApp bot orders.
- Remaining contract risk: WhatsApp catalog price override items still use the legacy fallback because the canonical cart item model does not store arbitrary per-item external prices.
