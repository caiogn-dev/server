# Pastita Server

Django REST Framework backend for the Pastita e-commerce platform.

## Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start server
python manage.py runserver
```

## Requirements

- Python 3.11+
- PostgreSQL 15+ (SQLite for development)
- Redis 7+

## Features

- E-commerce API (Products, Cart, Checkout)
- Order Management with full lifecycle
- Payment Integration (Mercado Pago: PIX, Boleto, Card)
- Delivery zone management with KM-based pricing (unified `CheckoutService._calculate_dynamic_fee`)
- WhatsApp Business API integration with conversational checkout flow
- AI-powered WhatsApp automation pipeline (`UnifiedService` → deterministic intent handlers → LLM agents)
- AutoMessage template system for order status notifications (with direct fallback for unconfigured stores)
- HERE Maps geocoding + reverse geocoding, structured address components propagated to orders
- Real-time WebSocket updates via Django Channels (`store_{slug}_orders` group)
- Langflow LLM automation
- Email notifications (Resend)
- Export functionality (CSV/Excel)

## Testing

All tests use Django's built-in `TestCase` (not pytest). Tests live in `server2/tests/`.

```bash
# Run all tests (Docker)
make test

# Run specific test module (local)
python manage.py test tests.test_whatsapp_order_service --keepdb -v 2

# Key test modules
python manage.py test tests.test_whatsapp_order_service   # WhatsApp order creation + _build_delivery_address
python manage.py test tests.test_automessage_dispatch      # AutoMessage/signal deduplication regression
python manage.py test tests.test_delivery_pricing_unified  # Unified fee formula + maps view fix
python manage.py test tests.test_session_address_components # HERE Maps address_components session flow
python manage.py test tests.test_checkout_service          # CheckoutService core logic
python manage.py test tests.test_checkout_e2e             # End-to-end checkout scenarios
```

### Test Conventions

- Module-level `_make_*()` helpers create isolated fixtures (not `setUpTestData`)
- External dependencies (MercadoPago, Redis, HERE Maps, Celery tasks) are always mocked with `@patch`
- Patch paths use the import location in the consuming module (e.g. `apps.whatsapp.services.order_service.broadcast_order_event`)
- `--keepdb` speeds up repeated runs by reusing the test database schema

## Documentation

See `/docs` folder in the project root for:
- [Technical Evaluation](../docs/TECHNICAL_EVALUATION.md)
- [API Reference](../docs/API_REFERENCE.md)
- [Deployment Guide](../docs/DEPLOYMENT.md)
- [HERE Maps Integration](../docs/HERE_MAPS_INTEGRATION.md)
- [Pending Tasks](../docs/TODO.md)

## API Documentation

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI Schema: `/api/schema/`

## License

MIT License
