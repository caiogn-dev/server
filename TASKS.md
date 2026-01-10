# Server Backend - Tasks

## 📋 Overview

Django REST Framework backend for Pastita e-commerce platform.
Includes: E-commerce, Orders, Payments, WhatsApp, Langflow integrations.

**Completude Estimada: 95% (atualizado 2026-01-10)**

---

## ✅ Completed (2026-01-10)

### E-commerce API
- [x] Products CRUD with categories and stock
- [x] Cart management (add, remove, update items)
- [x] Checkout flow with order creation
- [x] `/checkout/status/` endpoint - returns order details, items, payment data
- [x] Wishlist model and API (add, remove, toggle favorites)
- [x] Coupon model with validation and discount calculation
- [x] DeliveryZone model with fee calculation by ZIP code

### Payment Integration
- [x] Mercado Pago service with PIX, Boleto, Card support
- [x] `create_pix_payment()` - generates QR code
- [x] `create_boleto_payment()` - generates ticket URL
- [x] `create_card_payment()` - processes card payment
- [x] Webhook handling for payment notifications (basic)

### User Management
- [x] UserProfile model with extended fields (phone, cpf, address)
- [x] Profile endpoint (`/users/profile/`)
- [x] Orders history endpoint (`/orders/history/`)

### Core Infrastructure
- [x] Authentication (Token-based)
- [x] CSRF protection
- [x] Export views (CSV/Excel) - backend ready
- [x] Dashboard overview endpoints
- [x] Health check endpoints

---

## ✅ High Priority - COMPLETED

### Mercado Pago Production
- [x] Configure production access token
- [x] Test PIX payment flow end-to-end
- [x] Test Boleto payment flow
- [x] Test Card payment flow
- [x] **CRITICAL:** Webhook signature validation implemented
  - Arquivo: `apps/ecommerce/services/mercado_pago_service.py`
  - Valida `x-signature` header com HMAC-SHA256

### Notifications System
- [x] **Email notifications on order status change**
  - Arquivo: `apps/notifications/services/email_service.py`
  - Templates: order_confirmed, payment_received, shipped, delivered
- [x] **Email notifications on payment events**
  - Templates: payment_pending, payment_confirmed, payment_failed
- [x] **WhatsApp notifications integration**
  - Integrado com `apps/whatsapp/services/`
  - Templates para cada status de pedido

### Order Management
- [x] Order cancellation with stock restoration
  - Arquivo: `apps/orders/repositories/order_repository.py`
  - Método: `cancel()` restaura `Product.stock_quantity`
- [x] Partial refund support
  - Arquivo: `apps/payments/services/payment_service.py`

### Security
- [x] Rate limiting on checkout endpoint
  - Decorator customizado: `@rate_limit(key_prefix='checkout', max_requests=5, window_seconds=60)`
  - Arquivo: `apps/ecommerce/api/views.py` → `CheckoutViewSet`
- [x] Input validation for CPF (algoritmo completo)
  - Arquivo: `apps/core/utils.py` → `validate_cpf()`
  - Integrado no checkout para PIX/Boleto

---

## ✅ Admin API Endpoints (COMPLETED)

### Admin API Endpoints (para Dashboard)
- [x] **Coupon CRUD via admin API**
  - Arquivo: `apps/ecommerce/api/views.py` → `CouponAdminViewSet` (linha 1744)
  - Endpoints: GET/POST/PUT/DELETE `/api/v1/ecommerce/admin/coupons/`
  - Inclui: toggle_active, stats
- [x] **Delivery zones CRUD via admin API**
  - Arquivo: `apps/ecommerce/api/views.py` → `DeliveryZoneAdminViewSet` (linha 1809)
  - Endpoints: GET/POST/PUT/DELETE `/api/v1/ecommerce/admin/delivery-zones/`
  - Inclui: toggle_active, stats
- [x] **Products CRUD via admin API**
  - Arquivo: `apps/ecommerce/api/views.py` → `ProductAdminViewSet` (linha 1724)
  - Endpoints: GET/POST/PUT/DELETE `/api/v1/ecommerce/admin/products/`
  - Inclui: upload de imagem, filtros, ordenação
- [x] **Store Location API**
  - Arquivo: `apps/ecommerce/api/views.py` → `StoreLocationAdminViewSet` (linha 1879)
  - Endpoints: GET/POST `/api/v1/ecommerce/admin/store-location/`

---

## 🟡 Medium Priority - TODO

### Analytics Endpoints
- [ ] Sales statistics endpoint
  - Arquivo: `apps/core/dashboard_views.py`
  - Métricas: vendas por dia/semana/mês, ticket médio
- [ ] Product performance metrics
  - Produtos mais vendidos, estoque baixo
- [ ] Customer analytics
  - Clientes recorrentes, LTV
- [ ] Payment method breakdown
  - % PIX vs Cartão vs Boleto

### Export Features
- [ ] Bulk product import (CSV)
- [ ] Bulk product export (CSV/Excel)
- [ ] Order export improvements (filtros por data)

---

## 🟢 Low Priority - TODO

### Performance
- [ ] Redis caching for products
  ```python
  # apps/ecommerce/api/views.py
  from django.core.cache import cache
  # Cache products list por 5 minutos
  ```
- [ ] Database query optimization
  - Usar `select_related` e `prefetch_related`
- [ ] Celery tasks for heavy operations
  - Email sending
  - Report generation
  - Webhook processing

### Documentation
- [ ] OpenAPI schema updates
- [ ] API usage examples
- [ ] Webhook integration guide

### Address Validation
- [ ] Integração com API de CEP (ViaCEP já usado no frontend)
- [ ] Validação de endereço completo

---

## 📁 Models Structure

### E-commerce (`apps/ecommerce/models.py`)
```python
Product         # name, price, category, stock_quantity, image, image_url, sku
Cart            # user, session_key, phone_number
CartItem        # cart, product, quantity
Checkout        # order, payment_status, customer info, shipping, pix_code, pix_qr_code
Wishlist        # user, products (M2M)
Coupon          # code, discount_type, discount_value, min_purchase, max_discount, validity
DeliveryZone    # name, zip_code_start, zip_code_end, delivery_fee, estimated_days
```

### Orders (`apps/orders/models.py`)
```python
Order           # order_number, status, total, customer, shipping_address
OrderItem       # order, product_id, product_name, quantity, unit_price
OrderEvent      # order, event_type, description, old_status, new_status
```

### Payments (`apps/payments/models.py`)
```python
Payment         # order, amount, status, gateway, payment_method, pix_code, qr_code
PaymentGateway  # name, gateway_type, is_enabled, configuration
```

### Core (`apps/core/models.py`)
```python
BaseModel       # id (UUID), created_at, updated_at, is_active
UserProfile     # user, phone, cpf, address, city, state, zip_code
```

---

## 🔌 API Endpoints

### E-commerce (Public)
```
GET    /api/v1/ecommerce/products/
GET    /api/v1/ecommerce/products/{id}/
GET    /api/v1/ecommerce/products/categories/
GET    /api/v1/ecommerce/products/search/?q=term
GET    /api/v1/ecommerce/cart/list/
POST   /api/v1/ecommerce/cart/add_item/
POST   /api/v1/ecommerce/cart/update_item/
POST   /api/v1/ecommerce/cart/remove_item/
POST   /api/v1/ecommerce/cart/clear/
POST   /api/v1/ecommerce/checkout/create_checkout/
GET    /api/v1/ecommerce/checkout/status/?order_number=xxx
GET    /api/v1/ecommerce/wishlist/
POST   /api/v1/ecommerce/wishlist/add/
POST   /api/v1/ecommerce/wishlist/remove/
POST   /api/v1/ecommerce/wishlist/toggle/
POST   /api/v1/ecommerce/coupons/validate/
POST   /api/v1/ecommerce/delivery/calculate/
GET    /api/v1/ecommerce/delivery/zones/
GET    /api/v1/ecommerce/orders/history/
```

### Core/Auth
```
GET    /api/v1/csrf/
POST   /api/v1/auth/login/
POST   /api/v1/auth/logout/
POST   /api/v1/auth/register/
GET    /api/v1/auth/me/
POST   /api/v1/auth/change-password/
GET    /api/v1/users/profile/
PATCH  /api/v1/users/profile/
```

### Orders (Admin)
```
GET    /api/v1/orders/
GET    /api/v1/orders/{id}/
POST   /api/v1/orders/
POST   /api/v1/orders/{id}/confirm/
POST   /api/v1/orders/{id}/awaiting_payment/
POST   /api/v1/orders/{id}/mark_paid/
POST   /api/v1/orders/{id}/ship/
POST   /api/v1/orders/{id}/deliver/
POST   /api/v1/orders/{id}/cancel/
POST   /api/v1/orders/{id}/add_item/
POST   /api/v1/orders/{id}/add_note/
GET    /api/v1/orders/{id}/events/
GET    /api/v1/orders/stats/
GET    /api/v1/orders/by_customer/?phone=xxx
```

### Payments (Admin)
```
GET    /api/v1/payments/
GET    /api/v1/payments/{id}/
POST   /api/v1/payments/
POST   /api/v1/payments/{id}/process/
POST   /api/v1/payments/{id}/confirm/
POST   /api/v1/payments/{id}/fail/
POST   /api/v1/payments/{id}/cancel/
POST   /api/v1/payments/{id}/refund/
GET    /api/v1/payments/by_order/?order_id=xxx
GET    /api/v1/payments/gateways/
POST   /api/v1/payments/gateways/
PATCH  /api/v1/payments/gateways/{id}/
DELETE /api/v1/payments/gateways/{id}/
```

### Webhooks (Public)
```
POST   /webhooks/whatsapp/
POST   /webhooks/payments/{gateway_id}/
POST   /webhooks/automation/
POST   /api/v1/ecommerce/webhooks/mercado_pago/
```

### Dashboard
```
GET    /api/v1/dashboard/overview/
GET    /api/v1/dashboard/activity/
GET    /api/v1/dashboard/charts/
```

### Export
```
GET    /api/v1/export/messages/
GET    /api/v1/export/orders/
GET    /api/v1/export/sessions/
GET    /api/v1/export/automation-logs/
GET    /api/v1/export/conversations/
GET    /api/v1/export/payments/
```

---

## 📊 Progress Summary

| Module | Status | Completude |
|--------|--------|------------|
| Products API | ✅ Complete | 100% |
| Cart API | ✅ Complete | 100% |
| Checkout API | ✅ Complete | 100% |
| Order Status API | ✅ Complete | 100% |
| Wishlist API | ✅ Complete | 100% |
| Coupon API (validate) | ✅ Complete | 100% |
| Coupon Admin CRUD | ✅ Complete | 100% |
| Delivery API (calculate) | ✅ Complete | 100% |
| Delivery Admin CRUD | ✅ Complete | 100% |
| PIX Payment | ✅ Complete | 100% |
| Boleto Payment | ✅ Complete | 100% |
| Card Payment | ✅ Complete | 100% |
| Webhook Validation | ✅ Complete | 100% |
| Email Notifications | ✅ Complete | 100% |
| WhatsApp Notifications | ✅ Complete | 100% |
| Products Admin CRUD | ✅ Complete | 100% |
| Export Features | ✅ Complete | 100% |
| CPF Validation | ✅ Complete | 100% |

---

## 🔧 Environment Variables

```env
# Django
DJANGO_SECRET_KEY=xxx
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=domain.com

# Database
DATABASE_URL=postgres://user:pass@host:5432/db
# ou para SQLite (dev)
# DB_ENGINE=sqlite3

# Redis/Celery
REDIS_URL=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/0

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN=xxx
MERCADO_PAGO_PUBLIC_KEY=xxx

# Email (para notificações)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=xxx
EMAIL_HOST_PASSWORD=xxx
EMAIL_USE_TLS=True

# WhatsApp (Meta)
WHATSAPP_API_VERSION=v18.0
WHATSAPP_WEBHOOK_VERIFY_TOKEN=xxx
WHATSAPP_APP_SECRET=xxx

# Langflow (opcional)
LANGFLOW_API_URL=http://localhost:7860
LANGFLOW_API_KEY=xxx

# CORS
CORS_ALLOWED_ORIGINS=https://cardapio.domain.com,https://admin.domain.com
```

---

## 🚀 Próximos Passos Recomendados

1. **Implementar webhook signature validation** (Mercado Pago)
2. **Criar serviço de email** com templates
3. **Adicionar admin endpoints** para cupons e zonas de entrega
4. **Implementar rate limiting** no checkout
5. **Adicionar testes automatizados** para fluxos críticos

---
*Last updated: 2026-01-10*

---

## ✅ Completed Tasks (2026-01-10 - Sessão 2)

### Payment Methods
- [x] **Pagamento em dinheiro** - `PaymentMethod.CASH` adicionado
- [x] **Processamento cash_on_delivery** - Pedido fica como "Aguardando Pagamento"

### Checkout Scheduling
- [x] **Campos de agendamento** no modelo Checkout:
  - `shipping_method` (delivery/pickup)
  - `scheduled_date` (DateField)
  - `scheduled_time_slot` (CharField)

### Email Notifications
- [x] **EmailService** criado com Resend:
  - `send_order_confirmation()`
  - `send_payment_confirmed()`
  - `send_order_shipped()`
  - `send_order_delivered()`

### Admin API
- [x] **CouponAdminViewSet** - CRUD completo + stats + toggle_active
- [x] **DeliveryZoneAdminViewSet** - CRUD completo + stats + toggle_active

### Endpoints Novos
```
GET/POST   /api/v1/ecommerce/admin/coupons/
GET/PATCH/DELETE /api/v1/ecommerce/admin/coupons/{id}/
POST       /api/v1/ecommerce/admin/coupons/{id}/toggle_active/
GET        /api/v1/ecommerce/admin/coupons/stats/

GET/POST   /api/v1/ecommerce/admin/delivery-zones/
GET/PATCH/DELETE /api/v1/ecommerce/admin/delivery-zones/{id}/
POST       /api/v1/ecommerce/admin/delivery-zones/{id}/toggle_active/
GET        /api/v1/ecommerce/admin/delivery-zones/stats/
```

---

## ✅ COMPLETED - Sessão 3 (2026-01-10)

### Migrations
- [x] `python manage.py makemigrations ecommerce` (campos de agendamento)
- [x] `python manage.py migrate`

### Email Integration
- [x] Integrar EmailService nos eventos de pedido (OrderService)
  - `_notify_customer_order_confirmed()` - Envia email de confirmação
  - `_notify_customer_payment_confirmed()` - Envia email de pagamento confirmado
  - `_notify_customer_order_shipped()` - Envia email de pedido enviado
  - `_notify_customer_order_delivered()` - Envia email de pedido entregue

### Security
- [x] Webhook signature validation (Mercado Pago)
  - Método: `verify_webhook_signature()` em `mercado_pago_service.py`
  - Valida HMAC-SHA256 do header x-signature
- [x] Rate limiting no checkout
  - Decorator: `@rate_limit(key_prefix='checkout', max_requests=5, window_seconds=60)`
  - Limita 5 checkouts por minuto por usuário/IP

---

## 📊 Progress Summary (Atualizado)

| Module | Status | Completude |
|--------|--------|------------|
| Products API | ✅ Complete | 100% |
| Cart API | ✅ Complete | 100% |
| Checkout API | ✅ Complete | 100% |
| Order Status API | ✅ Complete | 100% |
| Wishlist API | ✅ Complete | 100% |
| Coupon API (validate) | ✅ Complete | 100% |
| **Coupon Admin CRUD** | ✅ Complete | **100%** |
| Delivery API (calculate) | ✅ Complete | 100% |
| **Delivery Admin CRUD** | ✅ Complete | **100%** |
| PIX Payment | ✅ Complete | 100% |
| Boleto Payment | ✅ Complete | 100% |
| Card Payment | ✅ Complete | 100% |
| **Webhook Validation** | ✅ Complete | **100%** |
| **Email Notifications** | ✅ Complete | **100%** |
| WhatsApp Notifications | ✅ Complete | 100% |
| Products Admin CRUD | 🟡 Partial | 50% |
| Export Features | ✅ Backend Ready | 100% |
| **Rate Limiting** | ✅ Complete | **100%** |

**Completude Geral: ~97%**

---
*Last updated: 2026-01-10*

---

## ✅ Atualização - Entrega por KM (2026-01-10)

- [x] StoreLocation model + admin endpoint
- [x] DeliveryZone com faixas por KM (min_km/max_km, preço por KM, taxa mínima)
- [x] Cálculo de rota (OSRM) com fallback Haversine
- [x] Cache de geolocalização de CEP (ZipCodeGeo)
- [x] /delivery/calculate retorna distance_km e rate_per_km

**Novos endpoints:**
```
GET  /api/v1/ecommerce/admin/store-location/
POST /api/v1/ecommerce/admin/store-location/
```
