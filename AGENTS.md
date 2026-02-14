# Server (Backend) - Repository Knowledge

Django backend for Pastita e-commerce system with WhatsApp integration.

## Tech Stack
- **Framework**: Django 4.x + Django REST Framework
- **WebSockets**: Django Channels
- **Database**: PostgreSQL
- **Cache/Broker**: Redis
- **Task Queue**: Celery

## Project Structure
```
apps/
├── stores/          # E-commerce: orders, products, cart, checkout
├── whatsapp/        # WhatsApp Cloud API integration
├── conversations/   # Conversation management
├── core/            # Base consumers, middleware, utilities
├── marketing/       # Email automation, campaigns
├── payments/        # Payment processing (MercadoPago)
└── users/           # User management, auth
```

## Key Files

### Stores App
- `apps/stores/api/views/storefront_views.py` - Public storefront endpoints (checkout, cart)
- `apps/stores/api/views/order_views.py` - Order management (authenticated)
- `apps/stores/api/serializers.py` - All store serializers
- `apps/stores/services/checkout_service.py` - Checkout logic, payment creation
- `apps/stores/services/cart_service.py` - Cart management

### WhatsApp App
- `apps/whatsapp/consumers.py` - WebSocket consumers
- `apps/whatsapp/services/` - Message sending, webhook handling

## API Endpoints

### Store-specific (uses store slug)
```
POST /api/v1/stores/s/{store_slug}/checkout/
GET  /api/v1/stores/s/{store_slug}/catalog/
GET  /api/v1/stores/s/{store_slug}/cart/
POST /api/v1/stores/s/{store_slug}/cart/add/
```

### Global endpoints
```
GET  /api/v1/stores/orders/by-token/{access_token}/  # Public order access
GET  /api/v1/stores/orders/                           # Orders list (auth)
POST /api/v1/stores/orders/{id}/update_status/        # Update status
```

## WebSocket Endpoints
```
/ws/whatsapp/dashboard/     # Multi-account dashboard
/ws/whatsapp/{account_id}/  # Single account
```

## Checkout Flow

1. Frontend sends checkout data to `/api/v1/stores/s/{slug}/checkout/`
2. `StoreCheckoutView` extracts:
   - `customer_data`: name, email, phone
   - `delivery_data`: method, address, distance
   - `coupon_code`, `notes`, `payment_method`
3. `checkout_service.create_order()` creates order
4. `checkout_service.create_payment()` processes payment (PIX/card)
5. Returns order details with `access_token` for secure access

## Important Patterns

### Customer Data Mapping
Frontend sends: `customer_name`, `customer_email`, `customer_phone`
Backend expects: `name`, `email`, `phone` in `customer_data` dict

### Order Access Token
- Generated on order creation (`secrets.token_urlsafe(32)`)
- Used for public order status access without authentication
- Endpoint: `/api/v1/stores/orders/by-token/{token}/`

## Environment Variables
```
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
MERCADO_PAGO_ACCESS_TOKEN=...
BASE_URL=https://api.domain.com
FRONTEND_URL=https://store.domain.com
```

## Commands
```bash
python manage.py runserver           # Development
python manage.py migrate             # Run migrations
celery -A config worker -l info      # Start Celery worker
```
