# Idempotency Guide

## What is Idempotency?

An idempotent operation produces the same result regardless of how many times it's called. If a request fails and retries, the server processes it only once.

### Example

**Without idempotency:**
```
Client: POST /orders/ {items: [1,2,3]}
Server: Creates Order #123
Response: 201 Created

[Network timeout - client doesn't see response]

Client: Retries POST /orders/ {items: [1,2,3]}
Server: Creates Order #124 (duplicate!)
Response: 201 Created

Result: Customer charged twice! 💥
```

**With idempotency:**
```
Client: POST /orders/ {items: [1,2,3]}
        Header: Idempotency-Key: abc-123
Server: Creates Order #123, caches response with key
Response: 201 Created

[Network timeout - client doesn't see response]

Client: Retries POST /orders/ {items: [1,2,3]}
        Header: Idempotency-Key: abc-123 (same key)
Server: Sees key in cache, returns cached response immediately
Response: 201 Created (same as before)

Result: Only one order created! ✅
```

## Implementation

### Backend (Django/DRF)

```python
from apps.core.decorators import idempotent
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['POST'])
@idempotent(timeout=3600)  # Cache for 1 hour
def create_order(request):
    order = Order.objects.create(
        customer=request.user,
        items=request.data['items'],
    )
    return Response({'id': order.id, 'total': order.total})
```

### Frontend (TypeScript/React)

```typescript
import { v4 as uuidv4 } from 'uuid';

// Generate unique key for this operation
const idempotencyKey = uuidv4();

const response = await api.post('/orders/', orderData, {
    headers: {
        'Idempotency-Key': idempotencyKey,
    },
});

// On retry (manual or automatic), same key = same response
if (networkError) {
    const retryResponse = await api.post('/orders/', orderData, {
        headers: {
            'Idempotency-Key': idempotencyKey,  // Same key!
        },
    });
    // Returns same order ID
}
```

## Decorator Options

### @idempotent()

Makes endpoint idempotent. Automatically caches responses.

```python
@idempotent(
    idempotency_key_header='Idempotency-Key',  # Header name
    timeout=3600  # Cache for 1 hour
)
def my_view(request):
    ...
```

**Behavior:**
- `POST /endpoint` with `Idempotency-Key: xyz` → Execute, cache response for 1 hour
- `POST /endpoint` with same key within 1 hour → Return cached response (no execution)
- `POST /endpoint` without key → Always execute
- GET requests → Not cached (idempotent by nature)

### @require_idempotency_key()

Enforces the header. Request without it is rejected with 400.

```python
@require_idempotency_key
def process_payment(request):
    # Will reject if header missing
    ...
```

**Usage:**
- Safety-critical endpoints (payments, orders, etc.)
- Forces clients to think about idempotency

## HTTP Headers

### Request

```
POST /api/v1/orders/ HTTP/1.1
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
Authorization: Token abc123...
Content-Type: application/json

{"items": [1, 2, 3]}
```

**Header format:**
- UUIDv4: `550e8400-e29b-41d4-a716-446655440000`
- Or any string, but UUIDs recommended (guaranteed unique)

### Response

```
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "order-123",
  "total": 99.99,
  "items": [...]
}
```

**Note:** Server doesn't echo the `Idempotency-Key` back (it's internal).

## Key Management

### When to Generate a New Key

- ✅ New independent operation (new order, new payment, etc.)
- ✅ User initiates request (click button, submit form)
- ✅ Before each POST/PUT/PATCH/DELETE

### When to Reuse Key

- ✅ Automatic client retry (same request, network error)
- ✅ User clicks "Retry" button
- ✅ Conditional retry logic (e.g., 5XX errors)

### When to NOT Use

- ❌ GET requests (read-only, naturally idempotent)
- ❌ HEAD/OPTIONS (read-only)
- ❌ Streaming responses (SSE, WebSocket)

## Best Practices

### 1. Always Use for Payments

```python
class PaymentViewSet(viewsets.ModelViewSet):
    @action(detail=False, methods=['post'])
    @require_idempotency_key
    def pay(self, request):
        # Payment is CRITICAL — force idempotency
        ...
```

### 2. Always Use for Orders

```python
class OrderViewSet(viewsets.ModelViewSet):
    @idempotent(timeout=3600)  # 1 hour
    def create(self, request):
        # Order creation should be idempotent
        ...
```

### 3. Use for Mutations

```python
@api_view(['POST', 'PUT', 'PATCH', 'DELETE'])
@idempotent()
def update_user(request):
    # Any write operation benefits from idempotency
    ...
```

### 4. Client Retry Logic

```typescript
async function createOrderWithRetry(data) {
    const idempotencyKey = uuidv4();
    const maxRetries = 3;
    
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            return await api.post('/orders/', data, {
                headers: { 'Idempotency-Key': idempotencyKey },
                timeout: 10000,
            });
        } catch (error) {
            if (attempt === maxRetries - 1) throw error;
            // Retry with same key = idempotent
            await delay(1000 * Math.pow(2, attempt));  // Exponential backoff
        }
    }
}
```

## Caching Behavior

### Default: 1 Hour

```python
@idempotent(timeout=3600)
def view(request):
    ...
```

### Longer: 24 Hours

```python
@idempotent(timeout=86400)
def payment_view(request):
    ...
```

### Custom: By Type

```python
class OrderViewSet(viewsets.ModelViewSet):
    def get_idempotency_timeout(self):
        if self.action == 'create':
            return 3600  # 1 hour for creation
        elif self.action == 'cancel':
            return 86400  # 24 hours for cancellation
        return 600  # 10 min default

    @idempotent(timeout=...)
    def create(self, request):
        ...
```

## Troubleshooting

### "Idempotency key not working"

**Check:**
1. Header name matches exactly: `Idempotency-Key` (case-sensitive)
2. Decorator applied: `@idempotent()`
3. Cache backend configured (Redis)
4. Method is POST/PUT/PATCH/DELETE (not GET)

### "Getting different response on retry"

**Causes:**
1. Cache expired (key older than timeout)
2. Different user (idempotency is per-user)
3. Different key used on retry
4. Cache backend down (fallback to execute)

### "Payments doubled despite idempotency"

**Likely:**
1. Idempotency decorator not on payment endpoint
2. External payment gateway not idempotent (Stripe webhook retry)
3. Database transaction not atomic

**Solution:**
```python
@require_idempotency_key
@transaction.atomic
def process_payment(request):
    # Enforce idempotency + transaction safety
    ...
```

## Testing

```bash
pytest apps/core/tests/test_idempotency.py -v
```

Tests verify:
- ✅ Same key = cached response
- ✅ Different keys = separate execution
- ✅ No key = always execute
- ✅ Per-user isolation
- ✅ Works with DELETE
- ✅ Enforced with decorator

## References

- Stripe Idempotent Requests: https://stripe.com/docs/api/idempotent_requests
- RFC 9110 Idempotent Methods: https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2
- Django Cache: https://docs.djangoproject.com/en/stable/topics/cache/
