# Pastita E-commerce API

Complete RESTful API built with Django & Django REST Framework with Mercado Pago payment integration for pastita.com.br

## 🚀 Quick Start

### Prerequisites
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a
- Python 3.11+
- pip (Python package manager)
- Mercado Pago Account (for payments)
- AWS S3 Account (for media storage)

### 1. Clone and Setup

```bash
# Navigate to project
cd server-main

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 2. Install Dependencies
<<<<<<< HEAD
=======
=======
- Python 3.13+
- Virtual Environment (already created at `/venv/`)
- Mercado Pago Account

### 1. Activate Virtual Environment

**Windows (PowerShell):**
```powershell
cd c:\Users\User\Documents\api\server
..\..\venv\Scripts\Activate.ps1
```

**Mac/Linux:**
```bash
cd ~/api/server
source ../../venv/bin/activate
```

### 2. Install Dependencies (Already Done)
>>>>>>> 838554ebd8a2ea491b313a8ada579af71a2b6d65
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a
Create `.env` file in the project root:
```env
DEBUG=True
SECRET_KEY=your-secret-key-here

# Database (uses SQLite in dev, PostgreSQL in production)
DATABASE_URL=sqlite:///db.sqlite3

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN=your-mercado-pago-token

# URLs
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:12001

# AWS S3 (for media files)
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=sa-east-1
<<<<<<< HEAD
=======
=======
Create `.env` file in `server/` directory:
```
DEBUG=True
SECRET_KEY=your-secret-key-here
MERCADO_PAGO_ACCESS_TOKEN=your-mercado-pago-token
BACKEND_URL=http://localhost:8000
FRONTEND_URL=https://pastita.com.br
>>>>>>> 838554ebd8a2ea491b313a8ada579af71a2b6d65
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a
```

Get your Mercado Pago token from: https://www.mercadopago.com/developers

<<<<<<< HEAD
### 4. Run Migrations
=======
<<<<<<< HEAD
### 4. Run Migrations
=======
### 4. Run Migrations (Already Done)
>>>>>>> 838554ebd8a2ea491b313a8ada579af71a2b6d65
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a
```bash
python manage.py migrate
```

### 5. Create Admin User
```bash
python manage.py createsuperuser
```

### 6. Start Server
```bash
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a
python manage.py runserver 0.0.0.0:12000
```

Server runs at: **http://localhost:12000**
<<<<<<< HEAD
=======
=======
python manage.py runserver
```

Server runs at: **http://localhost:8000**
>>>>>>> 838554ebd8a2ea491b313a8ada579af71a2b6d65
>>>>>>> 13838eb33aed8bbccef57ffcdb6234c3511ad18a

---

## 📚 API Overview

### Base URL
```
http://localhost:8000/api/
```

### Admin Panel
```
http://localhost:8000/admin/
```

### API Root (Browsable)
```
http://localhost:8000/api/
```

---

## 🔑 Database Models (ORM)

### 1. **User** (Extended Django User)
```python
- id (UUID)
- username, email, password
- first_name, last_name
- phone, cpf, date_of_birth
- profile_image
- address, city, state, zip_code, country
- created_at, updated_at
```

### 2. **Product**
```python
- id (UUID)
- name, description, price
- stock_quantity
- image
- category, sku
- is_active (boolean)
- created_at, updated_at
```

### 3. **Cart**
```python
- id (UUID)
- user (1-to-1 relationship)
- items (related CartItems)
- created_at, updated_at
- Methods: get_total(), get_item_count()
```

### 4. **CartItem**
```python
- id (UUID)
- cart (Foreign Key)
- product (Foreign Key)
- quantity
- created_at, updated_at
```

### 5. **Order**
```python
- id (UUID)
- user (Foreign Key)
- order_number (unique)
- total_amount
- status (pending, processing, shipped, delivered, cancelled)
- shipping_address, shipping_city, shipping_state, shipping_zip_code
- notes
- created_at, updated_at
```

### 6. **OrderItem**
```python
- id (UUID)
- order (Foreign Key)
- product (Foreign Key)
- quantity, price
- created_at
```

### 7. **Checkout**
```python
- id (UUID)
- order (1-to-1)
- user (Foreign Key)
- total_amount
- payment_status
- payment_method
- mercado_pago_payment_id
- mercado_pago_preference_id
- session_token (unique)
- payment_link
- customer_name, customer_email, customer_phone
- billing_address, city, state, zip_code
- expires_at, completed_at
- created_at, updated_at
```

### 8. **PaymentNotification**
```python
- id (UUID)
- notification_type (payment, order, merchant_order)
- mercado_pago_id (unique)
- checkout (Foreign Key)
- payload (JSON)
- status, status_detail
- processed (boolean)
- error_message
- created_at, processed_at
```

---

## 🛣️ API Endpoints

### User Management
```
POST   /api/users/register/                    - Register new user
GET    /api/users/profile/                    - Get current user profile
PUT    /api/users/profile/                    - Update user profile
```

### Products
```
GET    /api/products/                         - List all products
GET    /api/products/{id}/                    - Get product details
GET    /api/products/search/?q=term           - Search products
GET    /api/products/categories/              - Get all categories
```

### Cart
```
GET    /api/cart/list/                        - Get user's cart
POST   /api/cart/add_item/                    - Add item to cart
POST   /api/cart/update_item/                 - Update item quantity
POST   /api/cart/remove_item/                 - Remove item from cart
POST   /api/cart/clear/                       - Clear entire cart
```

### Orders
```
GET    /api/orders/                           - List user's orders
GET    /api/orders/{id}/                      - Get order details
GET    /api/orders/{id}/items/                - Get order items
PATCH  /api/orders/{id}/update_status/        - Update order status (admin)
```

### Checkout
```
POST   /api/checkout/create_checkout/         - Create checkout from cart
GET    /api/checkout/list/                    - Get user's checkouts
GET    /api/checkout/details/?token=...       - Get checkout by token
```

### Webhooks
```
POST   /api/webhooks/mercado_pago/            - Mercado Pago webhook receiver
```

---

## 💳 Mercado Pago Integration Flow

```
┌─────────────────┐
│   Frontend      │
│  (pastita.com)  │
└────────┬────────┘
         │
         ├─→ POST /api/checkout/create_checkout/
         │
┌────────▼────────────────────────────────────────┐
│     Backend (Django API)                         │
│  ├─ Create Order                                │
│  ├─ Create Checkout                             │
│  └─ Create Mercado Pago Preference              │
└────────┬─────────────────────────────────────────┘
         │
         └─→ Return payment_link
         │
         ├─→ Redirect to Mercado Pago
         │
┌────────▼────────────────────────────────┐
│   Mercado Pago Payment Gateway           │
│   (User completes payment)               │
└────────┬─────────────────────────────────┘
         │
         ├─→ POST /api/webhooks/mercado_pago/
         │
         └─→ Redirect to Frontend (success/failure)
         │
┌────────▼─────────────────────────────────┐
│   Backend Updates Status                  │
│   ├─ Update Checkout payment_status       │
│   └─ Update Order status                  │
└───────────────────────────────────────────┘
```

---

## 🔐 Authentication

### Get Token (Development)
```bash
POST /api-auth/login/
```

### Use Token in Requests
```
Authorization: Token YOUR_TOKEN_HERE
```

Or with curl:
```bash
curl -H "Authorization: Token YOUR_TOKEN" http://localhost:8000/api/users/profile/
```

---

## 📝 Example Workflows

### 1. Register & Login
```javascript
// Register
const registerRes = await fetch('http://localhost:8000/api/users/register/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'joao123',
    email: 'joao@example.com',
    password: 'secure123',
    first_name: 'João',
    last_name: 'Silva'
  })
});
```

### 2. Add Product to Cart
```javascript
const cartRes = await fetch('http://localhost:8000/api/cart/add_item/', {
  method: 'POST',
  headers: {
    'Authorization': 'Token YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    product_id: 'product-uuid',
    quantity: 2
  })
});
```

### 3. Create Checkout
```javascript
const checkoutRes = await fetch('http://localhost:8000/api/checkout/create_checkout/', {
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

const checkout = await checkoutRes.json();
window.location.href = checkout.payment_link;  // Redirect to Mercado Pago
```

---

## 📂 Project Structure

```
c:\Users\User\Documents\api\
├── venv/                          # Virtual environment (activated)
│   └── Scripts/python.exe          # Python executable
│
└── server/
    ├── api/                       # Django app
    │   ├── migrations/            # Database migrations
    │   ├── models.py             # 8 ORM models
    │   ├── serializers.py        # DRF serializers
    │   ├── views.py              # API viewsets
    │   ├── urls.py               # API routes
    │   ├── admin.py              # Django admin config
    │   ├── permissions.py        # Custom permissions
    │   └── mercado_pago.py       # Mercado Pago service
    │
    ├── server/
    │   ├── settings.py           # Django settings
    │   ├── urls.py               # Main URL config
    │   ├── wsgi.py               # WSGI app
    │   └── asgi.py               # ASGI app
    │
    ├── logs/                      # Application logs
    ├── media/                     # User uploads
    ├── manage.py                  # Django CLI
    ├── db.sqlite3                 # Database
    ├── requirements.txt           # Dependencies
    ├── .env.example              # Environment template
    ├── .env                       # Environment (YOUR CONFIG)
    ├── API_DOCUMENTATION.md       # Full API docs
    └── README.md                  # This file
```

---

## ⚙️ Configuration

### CORS (Cross-Origin Resource Sharing)

Frontend domains allowed to access API:
- `http://localhost:3000` (dev)
- `http://localhost:8000` (dev)
- `https://pastita.com.br` (production)

To add more origins, edit `server/settings.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "your-domain.com",
    # Add more domains
]
```

### Media Files

User uploads stored in: `server/media/`

Accessible at: `http://localhost:8000/media/`

---

## 🧪 Testing

### Test with cURL
```bash
# List products
curl http://localhost:8000/api/products/

# Get cart (requires auth token)
curl -H "Authorization: Token YOUR_TOKEN" http://localhost:8000/api/cart/list/
```

### Test with Postman

1. Create collection with base URL: `http://localhost:8000/api/`
2. Add Authorization header: `Authorization: Token YOUR_TOKEN`
3. Test each endpoint

### Test Payment Webhook

```bash
curl -X POST http://localhost:8000/api/webhooks/mercado_pago/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "payment",
    "id": "123456789"
  }'
```

---

## 🚨 Troubleshooting

### Server Won't Start
```bash
# Check for migrations
python manage.py migrate

# Check for errors
python manage.py check
```

### Database Errors
```bash
# Reset database (development only)
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### Mercado Pago Token Not Working
1. Check `.env` file has correct token
2. Verify token at Mercado Pago dashboard
3. Token must have payment read/write permissions

### CORS Errors
Check frontend domain is in `CORS_ALLOWED_ORIGINS` in `settings.py`

---

## 📦 Dependencies

```
Django==6.0
djangorestframework==3.16.1
django-cors-headers==4.9.0
django-filter==25.2
mercadopago==2.3.0
python-decouple==3.8
python-dotenv==1.2.1
Pillow==12.1.0
requests==2.32.5
```

Install all: `pip install -r requirements.txt`

---

## 🔒 Security Notes

1. **Never commit `.env` file** - it contains secrets
2. **Use HTTPS in production** (not HTTP)
3. **Set DEBUG=False** in production
4. **Use strong SECRET_KEY** in production
5. **Validate all webhook signatures** from Mercado Pago
6. **Use environment variables** for all secrets
7. **Enable CORS only for trusted domains**

---

## 🚀 Deployment

For production deployment:

1. Use PostgreSQL instead of SQLite
2. Use Gunicorn/uWSGI as WSGI server
3. Configure proper logging
4. Set up HTTPS/SSL certificates
5. Use environment variables for all config
6. Set DEBUG=False
7. Configure allowed hosts
8. Set up proper database backups
9. Monitor error logs

---

## 📞 Support

- **Mercado Pago Docs**: https://www.mercadopago.com/developers
- **Django Docs**: https://docs.djangoproject.com/
- **DRF Docs**: https://www.django-rest-framework.org/

---

## ✅ Next Steps

1. ✅ API created with all models
2. ✅ Database migrations applied
3. ✅ Django admin configured
4. ✅ REST endpoints ready
5. ✅ Mercado Pago integration ready
6. ✅ Webhook handler ready
7. ✅ CORS configured
8. ⬜ Create admin user: `python manage.py createsuperuser`
9. ⬜ Add products via admin panel
10. ⬜ Configure `.env` with Mercado Pago token
11. ⬜ Connect frontend to API endpoints

---

**Status**: ✅ Ready for Integration

**Server**: http://localhost:8000
**Admin**: http://localhost:8000/admin/
**API Root**: http://localhost:8000/api/

Start the server anytime with:
```bash
python manage.py runserver
```

Good luck! 🎉
