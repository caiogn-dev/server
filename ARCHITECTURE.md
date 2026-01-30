# Server Architecture

## Overview

This Django backend serves multiple frontends:
- **pastita-3d**: Customer-facing storefront (React/Next.js)
- **pastita-dash**: Admin dashboard (React/TypeScript)

## App Structure

### Core Apps (Active)

| App | Purpose | Status |
|-----|---------|--------|
| `stores` | Multi-tenant store management | **Primary** |
| `whatsapp` | WhatsApp Business API integration | Active |
| `conversations` | Chat/conversation management | Active |
| `marketing` | Marketing campaigns and stats | Active |
| `automation` | Workflow automation | Active |
| `notifications` | Push notifications | Active |
| `audit` | Audit logging | Active |
| `core` | Shared utilities and base models | Active |

### Legacy Apps (Deprecated)

| App | Purpose | Replacement |
|-----|---------|-------------|
| `ecommerce` | Legacy e-commerce models | `stores` |
| `orders` | Legacy order management | `stores.StoreOrder` |
| `payments` | Generic payment processing | `stores` payment fields |

## Model Mapping

### Orders
- **Legacy**: `orders.Order` - Generic orders tied to WhatsApp conversations
- **New**: `stores.StoreOrder` - Multi-tenant store orders

### Products
- **Legacy**: `ecommerce.Product` - Single-tenant products
- **New**: `stores.StoreProduct` - Multi-tenant products with dynamic types

### Cart
- **Legacy**: `ecommerce.Cart`, `ecommerce.CartItem`
- **New**: `stores.StoreCart`, `stores.StoreCartItem`

### Coupons
- **Legacy**: `ecommerce.Coupon`
- **New**: `stores.StoreCoupon`

## API Endpoints

### Primary API (v1)
- `/api/v1/stores/` - Store management
- `/api/v1/stores/s/{slug}/` - Store-specific operations
- `/api/v1/stores/s/{slug}/products/` - Products
- `/api/v1/stores/s/{slug}/orders/` - Orders
- `/api/v1/stores/s/{slug}/categories/` - Categories
- `/api/v1/stores/s/{slug}/coupons/` - Coupons
- `/api/v1/stores/s/{slug}/delivery-zones/` - Delivery zones

### Legacy API (Deprecated)
- `/api/v1/orders/` - Legacy orders (mostly wrappers; prefer `/api/v1/stores/...`)
- Legacy e-commerce endpoints (migrated into `/api/v1/stores/`)

## Migration Guide

### For New Features
1. Always use `stores` app models
2. Use `StoreOrder` for orders
3. Use `StoreProduct` for products
4. Use `StoreCart` for shopping carts

### For Existing Code
1. Check if code uses legacy models
2. Plan migration to `stores` equivalents
3. Update imports and references
4. Test thoroughly before deploying

## Database Schema

The `stores` app uses the following tables:
- `stores` - Store configuration
- `store_products` - Products
- `store_categories` - Categories
- `store_orders` - Orders
- `store_order_items` - Order line items
- `store_carts` - Shopping carts
- `store_cart_items` - Cart items
- `store_coupons` - Discount coupons
- `store_delivery_zones` - Delivery areas
- `store_product_types` - Dynamic product types

## Environment Variables

```bash
# Database
DATABASE_URL=postgres://...

# Redis
REDIS_URL=redis://...

# Security
SECRET_KEY=...
ALLOWED_HOSTS=...

# External Services
MERCADOPAGO_ACCESS_TOKEN=...
WHATSAPP_API_TOKEN=...
```

## Development

```bash
# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver

# Run tests
python manage.py test
```
