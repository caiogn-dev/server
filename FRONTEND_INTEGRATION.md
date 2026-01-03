# Frontend Integration Guide

This guide explains how to connect your pastita.com.br frontend to the Django API backend.

## 🔗 API Base URL

```
Production: https://your-api-domain.com/api/
Development: http://localhost:8000/api/
```

## 🔐 Authentication

### Get Auth Token

First, get an authentication token for the user:

```javascript
async function login(username, password) {
  const response = await fetch('http://localhost:8000/api-auth/login/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password })
  });
  
  if (response.ok) {
    // Token will be in response or set via session cookie
    return response;
  }
}
```

Or use Token Authentication:

```javascript
async function getToken(username, password) {
  // You'll need to implement a custom token endpoint
  // For now, store token in localStorage after login
  const token = localStorage.getItem('authToken');
  return token;
}
```

### Add Token to Requests

```javascript
const token = localStorage.getItem('authToken');
const headers = {
  'Authorization': `Token ${token}`,
  'Content-Type': 'application/json',
};

const response = await fetch('http://localhost:8000/api/users/profile/', {
  method: 'GET',
  headers: headers
});
```

Or use a reusable fetch wrapper:

```javascript
class API {
  constructor(baseURL = 'http://localhost:8000/api') {
    this.baseURL = baseURL;
  }

  getHeaders() {
    const token = localStorage.getItem('authToken');
    return {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Token ${token}` })
    };
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        ...this.getHeaders(),
        ...options.headers,
      }
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  // User endpoints
  async registerUser(userData) {
    return this.request('/users/register/', {
      method: 'POST',
      body: JSON.stringify(userData)
    });
  }

  async getUserProfile() {
    return this.request('/users/profile/', { method: 'GET' });
  }

  async updateUserProfile(userData) {
    return this.request('/users/profile/', {
      method: 'PUT',
      body: JSON.stringify(userData)
    });
  }

  // Product endpoints
  async getProducts(filters = {}) {
    const params = new URLSearchParams(filters);
    return this.request(`/products/?${params}`, { method: 'GET' });
  }

  async getProduct(id) {
    return this.request(`/products/${id}/`, { method: 'GET' });
  }

  async searchProducts(query, category = '') {
    return this.request(`/products/search/?q=${query}&category=${category}`, {
      method: 'GET'
    });
  }

  async getCategories() {
    return this.request('/products/categories/', { method: 'GET' });
  }

  // Cart endpoints
  async getCart() {
    return this.request('/cart/list/', { method: 'GET' });
  }

  async addToCart(productId, quantity = 1) {
    return this.request('/cart/add_item/', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, quantity })
    });
  }

  async updateCartItem(productId, quantity) {
    return this.request('/cart/update_item/', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, quantity })
    });
  }

  async removeFromCart(productId) {
    return this.request('/cart/remove_item/', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId })
    });
  }

  async clearCart() {
    return this.request('/cart/clear/', { method: 'POST' });
  }

  // Order endpoints
  async getOrders() {
    return this.request('/orders/', { method: 'GET' });
  }

  async getOrder(id) {
    return this.request(`/orders/${id}/`, { method: 'GET' });
  }

  async getOrderItems(id) {
    return this.request(`/orders/${id}/items/`, { method: 'GET' });
  }

  // Checkout endpoints
  async createCheckout(checkoutData) {
    return this.request('/checkout/create_checkout/', {
      method: 'POST',
      body: JSON.stringify(checkoutData)
    });
  }

  async getCheckoutDetails(token) {
    return this.request(`/checkout/details/?token=${token}`, {
      method: 'GET'
    });
  }

  async getCheckouts() {
    return this.request('/checkout/list/', { method: 'GET' });
  }
}

// Usage
const api = new API('http://localhost:8000/api');
```

---

## 🛒 Shopping Cart Flow

### 1. Load Products

```javascript
async function loadProducts() {
  const products = await api.getProducts();
  displayProducts(products.results); // Paginated
}

async function searchProducts(query) {
  const results = await api.searchProducts(query);
  displayProducts(results);
}
```

### 2. Add to Cart

```javascript
async function addToCart(productId, quantity = 1) {
  try {
    const cartItem = await api.addToCart(productId, quantity);
    console.log('Added to cart:', cartItem);
    showNotification('Product added to cart!', 'success');
  } catch (error) {
    showNotification(error.message, 'error');
  }
}
```

### 3. View Cart

```javascript
async function viewCart() {
  const cart = await api.getCart();
  console.log('Cart total:', cart.total);
  console.log('Items:', cart.items);
  displayCart(cart);
}
```

### 4. Update Cart Item

```javascript
async function updateCartQuantity(productId, newQuantity) {
  if (newQuantity <= 0) {
    await removeFromCart(productId);
  } else {
    const updated = await api.updateCartItem(productId, newQuantity);
    updateCartDisplay(updated);
  }
}
```

---

## 💳 Checkout & Payment Flow

### 1. Create Checkout

```javascript
async function startCheckout() {
  const checkoutData = {
    customer_name: 'João Silva',
    customer_email: 'joao@example.com',
    customer_phone: '+5511987654321',
    billing_address: 'Rua Principal, 123',
    billing_city: 'São Paulo',
    billing_state: 'SP',
    billing_zip_code: '01234-567',
    billing_country: 'Brazil',
    payment_method: 'credit_card'
  };

  try {
    const checkout = await api.createCheckout(checkoutData);
    console.log('Checkout created:', checkout);
    
    // Save session token for later reference
    localStorage.setItem('checkoutToken', checkout.session_token);
    
    // Redirect to payment page
    window.location.href = checkout.payment_link;
  } catch (error) {
    showNotification('Checkout failed: ' + error.message, 'error');
  }
}
```

### 2. Handle Payment Success

After Mercado Pago redirects the user back to your success page:

```javascript
async function handlePaymentSuccess() {
  const token = new URLSearchParams(window.location.search).get('token');
  
  try {
    const checkout = await api.getCheckoutDetails(token);
    
    if (checkout.payment_status === 'completed') {
      showNotification('Payment successful! Order confirmed.', 'success');
      // Redirect to order confirmation page
      window.location.href = `/order-confirmed/${checkout.order.order_number}`;
    } else if (checkout.payment_status === 'processing') {
      showNotification('Payment is being processed.', 'info');
    } else {
      showNotification('Payment status: ' + checkout.payment_status, 'warning');
    }
  } catch (error) {
    showNotification('Could not verify payment', 'error');
  }
}
```

### 3. Handle Payment Failure

After Mercado Pago redirects to failure page:

```javascript
async function handlePaymentFailure() {
  const token = new URLSearchParams(window.location.search).get('token');
  
  try {
    const checkout = await api.getCheckoutDetails(token);
    showNotification(`Payment failed: ${checkout.payment_status}`, 'error');
    // Keep cart items so user can retry
  } catch (error) {
    showNotification('Payment verification failed', 'error');
  }
}
```

---

## 📊 Example React Component

```javascript
import React, { useState, useEffect } from 'react';

const ShoppingCart = () => {
  const [cart, setCart] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadCart();
  }, []);

  const loadCart = async () => {
    setLoading(true);
    try {
      const cartData = await api.getCart();
      setCart(cartData);
    } catch (error) {
      console.error('Failed to load cart:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateQuantity = async (productId, quantity) => {
    try {
      await api.updateCartItem(productId, quantity);
      await loadCart(); // Refresh cart
    } catch (error) {
      console.error('Failed to update cart:', error);
    }
  };

  const handleRemoveItem = async (productId) => {
    try {
      await api.removeFromCart(productId);
      await loadCart();
    } catch (error) {
      console.error('Failed to remove item:', error);
    }
  };

  const handleCheckout = async () => {
    const userData = await api.getUserProfile();
    
    const checkoutData = {
      customer_name: userData.first_name + ' ' + userData.last_name,
      customer_email: userData.email,
      customer_phone: userData.phone || '+55',
      billing_address: userData.address,
      billing_city: userData.city,
      billing_state: userData.state,
      billing_zip_code: userData.zip_code,
      billing_country: userData.country,
      payment_method: 'credit_card'
    };

    try {
      const checkout = await api.createCheckout(checkoutData);
      window.location.href = checkout.payment_link;
    } catch (error) {
      alert('Checkout error: ' + error.message);
    }
  };

  if (loading) return <div>Loading cart...</div>;
  if (!cart) return <div>No cart data</div>;

  return (
    <div className="cart">
      <h2>Shopping Cart</h2>
      <ul>
        {cart.items.map(item => (
          <li key={item.id}>
            <h3>{item.product.name}</h3>
            <p>R$ {item.product.price}</p>
            <input
              type="number"
              value={item.quantity}
              onChange={(e) => handleUpdateQuantity(item.product.id, e.target.value)}
            />
            <button onClick={() => handleRemoveItem(item.product.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <p>Total: R$ {cart.total}</p>
      <button onClick={handleCheckout}>Proceed to Checkout</button>
    </div>
  );
};

export default ShoppingCart;
```

---

## 🔄 Real-time Updates (Polling)

To keep cart updated across browser tabs:

```javascript
function startCartSync() {
  setInterval(async () => {
    try {
      const cart = await api.getCart();
      // Update UI with new cart data
      updateCartUI(cart);
    } catch (error) {
      console.error('Cart sync failed:', error);
    }
  }, 30000); // Check every 30 seconds
}
```

---

## 🚨 Error Handling

```javascript
async function apiRequest(endpoint, options) {
  try {
    const response = await fetch(`http://localhost:8000/api${endpoint}`, options);
    
    if (response.status === 401) {
      // Unauthorized - redirect to login
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    
    if (response.status === 403) {
      // Forbidden
      throw new Error('You do not have permission to do this');
    }
    
    if (response.status === 404) {
      throw new Error('Resource not found');
    }
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Unknown error');
    }
    
    return await response.json();
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
}
```

---

## 📝 API Response Examples

### Get Cart Response
```json
{
  "id": "uuid",
  "user": "uuid",
  "items": [
    {
      "id": "uuid",
      "product": {
        "id": "uuid",
        "name": "Product Name",
        "price": "99.99",
        "image": "/media/products/image.jpg"
      },
      "quantity": 2,
      "subtotal": "199.98"
    }
  ],
  "total": "299.97",
  "item_count": 3,
  "created_at": "2026-01-02T10:30:00Z"
}
```

### Checkout Response
```json
{
  "id": "uuid",
  "session_token": "unique-token",
  "payment_link": "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=123",
  "total_amount": "299.99",
  "payment_status": "pending",
  "payment_method": "credit_card",
  "order": {
    "id": "uuid",
    "order_number": "ORD-ABC123",
    "status": "pending",
    "total_amount": "299.99"
  },
  "created_at": "2026-01-02T10:30:00Z"
}
```

---

## 🔗 CORS Configuration

The API is configured to accept requests from:
- `http://localhost:3000` (local development)
- `https://pastita.com.br` (production)

If you need to add more domains, contact the API administrator.

---

## 💾 LocalStorage Keys

Recommended keys for storing frontend state:

```javascript
localStorage.setItem('authToken', 'token-value');           // Auth token
localStorage.setItem('userId', 'user-id');                 // Current user ID
localStorage.setItem('checkoutToken', 'checkout-token');   // Last checkout
localStorage.setItem('lastPaymentStatus', 'completed');    // Last payment status
```

---

## 🧪 Testing Checklist

- [ ] User registration works
- [ ] User login and token storage works
- [ ] Product listing loads correctly
- [ ] Product search works
- [ ] Adding items to cart works
- [ ] Removing items from cart works
- [ ] Updating cart quantities works
- [ ] Cart total calculates correctly
- [ ] Checkout form prepopulates with user data
- [ ] Checkout creation sends correct data
- [ ] Redirect to Mercado Pago payment page works
- [ ] Payment success page correctly verifies payment
- [ ] Order confirmation page displays order details
- [ ] User can view order history

---

## 📞 Support

For API issues:
- Check `API_DOCUMENTATION.md` in server directory
- Check Django admin panel at `/admin/`
- Review logs in `logs/django.log`
- Contact backend development team

For integration help:
- Review example requests above
- Test endpoints with Postman first
- Use browser console to debug requests
- Check network tab for response details
