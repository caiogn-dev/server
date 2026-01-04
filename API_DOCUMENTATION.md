# API Documentation

## E-commerce API with Django + Mercado Pago Integration

This is a complete RESTful API built with Django Rest Framework for an e-commerce platform with Mercado Pago payment integration.

### Features

- **User Management**: User registration and profile management
- **Product Catalog**: Full product management with search and filtering
- **Shopping Cart**: Add, update, remove items from cart
- **Orders**: Order creation and tracking
- **Checkout**: Checkout process with payment gateway
- **Mercado Pago Integration**: Payment processing and webhook handling
- **Admin Panel**: Django admin interface for managing all resources
- **CORS Support**: Integrated with frontend at pastita.com.br

---

## Installation & Setup

### Prerequisites

- Python 3.13+
- Virtual Environment (`venv/`)
- Mercado Pago account with API credentials

### 1. Environment Setup

```bash
# Navigate to project directory
cd c:\Users\User\Documents\api\server

# Activate virtual environment
..\..\venv\Scripts\Activate.ps1
```

### 2. Environment Variables

Create a `.env` file in the server directory based on `.env.example`:

```bash
DEBUG=True
SECRET_KEY=your-secret-key-here

# Mercado Pago API Token (get from https://www.mercadopago.com/developers)
MERCADO_PAGO_ACCESS_TOKEN=your-actual-access-token

# API URLs
BACKEND_URL=http://localhost:8000
FRONTEND_URL=https://pastita.com.br
```

### 3. Database

The API uses SQLite by default (suitable for development). For production, consider migrating to PostgreSQL.

```bash
# Migrations already applied
python manage.py migrate
```

### 4. Create Superuser

```bash
python manage.py createsuperuser
```

Follow the prompts to create an admin user.

### 5. Start Development Server

```bash
python manage.py runserver
```

Server will run at `http://localhost:8000`

---

## API Endpoints

### Base URL: `http://localhost:8000/api/`

### Authentication
- Token Authentication: Add header `Authorization: Token <your_token>`
- Session Authentication: Login via admin panel or `/api-auth/login/`

---

## User Endpoints

### Register User
```
POST /api/users/register/
Content-Type: application/json

{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "secure_password",
  "first_name": "John",
  "last_name": "Doe"
}
```

### Get User Profile
```
GET /api/users/profile/
Authorization: Token <your_token>
```

### Update User Profile
```
PUT /api/users/profile/
Authorization: Token <your_token>
Content-Type: application/json

{
  "phone": "11987654321",
  "cpf": "12345678901",
  "address": "Rua Principal, 123",
  "city": "São Paulo",
  "state": "SP",
  "zip_code": "01234-567",
  "country": "Brazil"
}
```

---

## Product Endpoints

### List Products
```
GET /api/products/
```

Query parameters:
- `category` - Filter by category
- `search` - Search by name or description
- `ordering` - Order by `price`, `created_at`, or `name`

### Search Products
```
GET /api/products/search/?q=notebook&category=electronics
```

### Get Product Categories
```
GET /api/products/categories/
```

### Get Product Details
```
GET /api/products/{id}/
```

---

## Cart Endpoints

### Get Cart
```
GET /api/cart/list/
Authorization: Token <your_token>
```

### Add Item to Cart
```
POST /api/cart/add_item/
Authorization: Token <your_token>
Content-Type: application/json

{
  "product_id": "uuid-of-product",
  "quantity": 2
}
```

### Update Cart Item Quantity
```
POST /api/cart/update_item/
Authorization: Token <your_token>
Content-Type: application/json

{
  "product_id": "uuid-of-product",
  "quantity": 5
}
```

### Remove Item from Cart
```
POST /api/cart/remove_item/
Authorization: Token <your_token>
Content-Type: application/json

{
  "product_id": "uuid-of-product"
}
```

### Clear Cart
```
POST /api/cart/clear/
Authorization: Token <your_token>
```

---

## Order Endpoints

### List User Orders
```
GET /api/orders/
Authorization: Token <your_token>
```

### Get Order Details
```
GET /api/orders/{id}/
Authorization: Token <your_token>
```

### Get Order Items
```
GET /api/orders/{id}/items/
Authorization: Token <your_token>
```

---

## Checkout Endpoints

### Create Checkout (from Cart)
```
POST /api/checkout/create_checkout/
Authorization: Token <your_token>
Content-Type: application/json

{
  "customer_name": "João Silva",
  "customer_email": "joao@example.com",
  "customer_phone": "+5511987654321",
  "billing_address": "Rua Principal, 123",
  "billing_city": "São Paulo",
  "billing_state": "SP",
  "billing_zip_code": "01234-567",
  "billing_country": "Brazil",
  "payment_method": "credit_card"
}
```

**Response:**
```json
{
  "id": "uuid",
  "session_token": "unique-token",
  "payment_link": "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=...",
  "total_amount": "299.99",
  "payment_status": "pending",
  "created_at": "2026-01-02T10:30:00Z"
}
```

### Get Checkout Details
```
GET /api/checkout/details/?token=unique-token
```

### List User Checkouts
```
GET /api/checkout/list/
Authorization: Token <your_token>
```

---

## Webhook Handling

### Mercado Pago Webhook
The API automatically receives payment notifications from Mercado Pago at:
```
POST /api/webhooks/mercado_pago/
```

**No authentication required** - Mercado Pago will POST updates directly to this endpoint.

The webhook payload is validated and processed to update order and checkout statuses.

---

## Payment Statuses

- `pending` - Awaiting payment
- `processing` - Payment being processed
- `completed` - Payment successful
- `failed` - Payment failed
- `cancelled` - Payment cancelled
- `refunded` - Payment refunded

---

## Order Statuses

- `pending` - Order created, awaiting payment
- `processing` - Payment confirmed, preparing shipment
- `shipped` - Order shipped
- `delivered` - Order delivered
- `cancelled` - Order cancelled

---

## Database Models

### User Model
- Extended Django User with CPF, phone, address, and profile image
- UUID as primary key
- Timestamps (created_at, updated_at)

### Product Model
- Name, description, price, stock quantity
- SKU for inventory tracking
- Category and image
- is_active flag
- Indices for fast queries on SKU and category

### Cart & CartItem
- One cart per user
- Multiple items per cart
- Methods for total and item count calculations

### Order & OrderItem
- Order tracking with unique order_number
- Multiple items per order
- Shipping address information
- Status tracking

### Checkout
- Links to order and user
- Payment gateway integration (Mercado Pago)
- Customer and billing information
- Payment status tracking
- Session token for secure payment links

### PaymentNotification
- Stores webhook notifications from Mercado Pago
- Tracks processing status
- Stores error messages for debugging

---

## Frontend Integration

### Frontend to Backend API Calls

Example with JavaScript (Fetch API):

```javascript
// Get user profile
const response = await fetch('http://localhost:8000/api/users/profile/', {
  headers: {
    'Authorization': 'Token YOUR_TOKEN'
  }
});
const user = await response.json();

// Add to cart
await fetch('http://localhost:8000/api/cart/add_item/', {
  method: 'POST',
  headers: {
    'Authorization': 'Token YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    product_id: 'product-uuid',
    quantity: 1
  })
});

// Create checkout
const checkoutResponse = await fetch('http://localhost:8000/api/checkout/create_checkout/', {
  method: 'POST',
  headers: {
    'Authorization': 'Token YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    customer_name: 'João Silva',
    customer_email: 'joao@example.com',
    customer_phone: '+5511987654321',
    billing_address: 'Rua Principal, 123',
    billing_city: 'São Paulo',
    billing_state: 'SP',
    billing_zip_code: '01234-567',
    payment_method: 'credit_card'
  })
});

const checkout = await checkoutResponse.json();
// Redirect user to payment_link
window.location.href = checkout.payment_link;
```

### Payment Flow

1. User adds products to cart
2. User clicks checkout
3. Frontend sends checkout data to `/api/checkout/create_checkout/`
4. Backend creates order and generates Mercado Pago preference
5. Backend returns `payment_link`
6. Frontend redirects user to `payment_link` (Mercado Pago's payment page)
7. User completes payment on Mercado Pago
8. Mercado Pago sends webhook notification to `/api/webhooks/mercado_pago/`
9. Backend updates order and checkout status
10. Mercado Pago redirects user back to your frontend (success/failure page)

---

## Admin Panel

Access admin at: `http://localhost:8000/admin/`

Manage:
- Users and profiles
- Products and inventory
- Carts and orders
- Checkouts and payments
- Payment notifications

---

## Security Considerations

1. **Never expose your Mercado Pago Access Token** in client-side code
2. Use HTTPS in production
3. Validate all webhook signatures (implement Mercado Pago verification)
4. Use environment variables for sensitive data
5. CORS is configured to allow your frontend domain

---

## Testing

### Create Sample Products

```python
from api.models import Product
from decimal import Decimal

Product.objects.create(
    name="Notebook Dell",
    description="Powerful laptop for work and gaming",
    price=Decimal("2999.99"),
    stock_quantity=10,
    category="electronics",
    sku="DELL-001",
    image="path/to/image.jpg"
)
```

### Test Payment Webhook

You can simulate a Mercado Pago webhook:

```bash
curl -X POST http://localhost:8000/api/webhooks/mercado_pago/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "payment",
    "id": "123456789"
  }'
```

---

## Troubleshooting

### Migrations Error
```bash
# Reset migrations (development only)
python manage.py migrate api zero
python manage.py migrate
```

### Mercado Pago Token Error
- Verify token is set in `.env`
- Check token is valid at Mercado Pago dashboard
- Ensure token has correct permissions

### CORS Issues
- Check CORS_ALLOWED_ORIGINS in settings.py
- Add your frontend domain if needed

### Cart Not Clearing After Checkout
- Check that checkout creation completed successfully
- Verify order and checkout objects were created

---

## Project Structure

```
api/
├── migrations/          # Database migrations
├── admin.py            # Django admin configuration
├── models.py           # Database models (7 models)
├── serializers.py      # DRF serializers
├── views.py            # API views and viewsets
├── urls.py             # API routing
├── permissions.py      # Custom permissions
├── mercado_pago.py     # Mercado Pago integration service
└── apps.py

server/
├── settings.py         # Django settings
├── urls.py             # Main URL configuration
├── wsgi.py             # WSGI application
├── asgi.py             # ASGI application
└── manage.py

.env.example            # Environment variables template
db.sqlite3              # SQLite database (development)
logs/                   # Application logs
media/                  # User-uploaded files
```

---

## Next Steps

1. **Configure Mercado Pago**: Get your access token from [Mercado Pago Developers](https://www.mercadopago.com/developers)
2. **Set Environment Variables**: Update `.env` with your credentials
3. **Create Sample Data**: Add products via admin panel
4. **Test Integration**: Use Postman or similar to test API endpoints
5. **Deploy Frontend**: Connect your pastita.com.br frontend to these API endpoints

---

## Support

For issues related to:
- **Mercado Pago**: https://www.mercadopago.com/developers
- **Django**: https://docs.djangoproject.com/
- **Django REST Framework**: https://www.django-rest-framework.org/

---

Last Updated: January 2, 2026
