# Rate Limiting Strategy

## Overview

Rate limiting protects the API from abuse, DoS attacks, and resource exhaustion. Implemented via DRF throttling.

## Configuration (config/settings/base.py)

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/minute',         # Public IP limit
        'user': '600/minute',         # Authenticated users
        'public_read': '300/minute',  # Storefront catalog (read)
        'public_write': '60/minute',  # Storefront cart (write)
        'checkout': '20/minute',      # Checkout (strict, anti-bot)
        'auth': '10/minute',          # Login/register (brute-force protect)
        'lead_create': '10/hour',     # Lead form (prevent spam)
        'webhook': '10000/hour',      # Webhook processing (high volume)
    }
}
```

## Rate Limits Explained

### 1. **Anonymous (120/minute)**
- Unauthenticated requests from IP
- Protects: API discovery, catalog browsing
- Allows: ~2 requests/second

### 2. **Authenticated User (600/minute)**
- Logged-in users get 5x higher limit
- Protects: Resource exhaustion
- Allows: ~10 requests/second

### 3. **Public Read (300/minute)**
- Storefront catalog viewing (GET)
- Higher than anon because read-only
- No impact on server (cached)

### 4. **Public Write (60/minute)**
- Storefront cart operations (POST/PUT)
- Lower because writes are expensive
- Prevents cart manipulation

### 5. **Checkout (20/minute)**
- Payment gateway operations
- **Most restrictive** — prevents:
  - Brute-force payment card testing
  - Double-charge attacks
  - Bot automation
- ~1 checkout per 3 seconds maximum

### 6. **Auth (10/minute)**
- Login, register, OTP endpoints
- **Very restrictive** — prevents:
  - Brute-force password guessing
  - OTP bypass attempts
  - Account enumeration

### 7. **Lead Form (10/hour)**
- Newsletter signup, contact forms
- Prevents spam bots
- Users can sign up once per 6 minutes

### 8. **Webhook (10000/hour)**
- Inbound webhooks (WhatsApp, MercadoPago, etc.)
- Very permissive — external integrations
- Equivalent to ~2.7 requests/second

## How It Works

### Request Flow

```
1. Request arrives
   ↓
2. DRF throttle class checks:
   - User identity (authenticated vs. anonymous)
   - Request path/viewset (which rate limit applies)
   - Cache: how many requests in last minute
   ↓
3. If under limit → Proceed (200 OK)
   ↓
4. If over limit → Return 429 Too Many Requests
   - Response includes: Retry-After header
   - Custom error message
```

### Example

```bash
# Request 1-600: succeeds (user rate limit)
$ curl -H "Authorization: Token abc123" https://api.example.com/orders/
200 OK

# Request 601: rate limited
$ curl -H "Authorization: Token abc123" https://api.example.com/orders/
429 Too Many Requests
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests. Please try again later.",
    "details": {"retry_after": 45}
  }
}
```

## View-Level Throttling

Override per view:

```python
from rest_framework.throttling import UserRateThrottle

class PaymentThrottle(UserRateThrottle):
    scope = 'checkout'  # Uses 20/minute rate

class PaymentViewSet(viewsets.ModelViewSet):
    throttle_classes = [PaymentThrottle]
```

## Testing

```bash
python manage.py test apps.core.tests.test_rate_limiting
```

Test scenarios:
1. ✅ Anonymous limit (120/min)
2. ✅ Authenticated limit (600/min)
3. ✅ Checkout strict (20/min)
4. ✅ 429 response format
5. ✅ Retry-After header

## Monitoring

Health check endpoint reports rate limit status:

```bash
curl https://api.example.com/api/v1/core/metrics/
{
  "services": {
    "rate_limiting": {
      "status": "healthy",
      "throttles_active": true,
      "cache_backend": "redis"
    }
  }
}
```

## Common Issues

### "I'm getting 429 but haven't made 120 requests"

**Causes:**
1. Shared IP (corporate network, VPN)
2. Rate limit includes multiple endpoints
3. Automatic client retries (browser, SDK)

**Solutions:**
- Use authentication (higher limit: 600/min)
- Implement client-side request queuing
- Space out requests (don't burst)

### "Rate limiting doesn't seem to work"

**Check:**
1. Cache backend configured (Redis required for production)
   ```python
   CACHES = {
       'default': {
           'BACKEND': 'django_redis.cache.RedisCache',
           'LOCATION': 'redis://redis:6379/1',
       }
   }
   ```

2. Throttle classes in REST_FRAMEWORK settings
3. Default throttle_classes or view-level throttle_classes

### "I need to increase limits for a specific user"

Options:
1. **Custom Throttle** — per user ID:
   ```python
   class VIPUserThrottle(UserRateThrottle):
       def get_rate(self):
           if self.request.user.is_premium:
               return '5000/minute'
           return '600/minute'
   ```

2. **Whitelist** — skip throttle for internal IPs:
   ```python
   class CustomThrottle(UserRateThrottle):
       THROTTLE_RATES = {'user': '600/minute'}
       
       def allow_request(self, request, view):
           if request.META['REMOTE_ADDR'] in INTERNAL_IPS:
               return True
           return super().allow_request(request, view)
   ```

## Production Checklist

- [ ] Redis configured and healthy
- [ ] Rate limits reviewed and appropriate
- [ ] Custom throttles per view if needed
- [ ] Monitoring alerts for high 429 rate
- [ ] Documentation for API consumers
- [ ] Load testing to verify limits work under stress
- [ ] Graceful degradation if cache fails

## References

- DRF Throttling: https://www.django-rest-framework.org/api-guide/throttling/
- Cache configuration: https://docs.djangoproject.com/en/stable/topics/cache/
