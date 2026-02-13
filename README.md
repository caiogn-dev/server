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
- Delivery zone management with KM-based pricing
- WhatsApp Business API integration
- Langflow LLM automation
- Real-time WebSocket updates
- Email notifications (Resend)
- Export functionality (CSV/Excel)

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
