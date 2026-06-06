# Combo API - URL Routing Configuration

**Updated**: 2026-06-06  
**Base Path**: `/api/v1/stores/`

---

## URL Pattern Summary

All combo endpoints follow the RESTful pattern:
- **Resource**: `{store_slug}/combos/`
- **Item**: `{store_slug}/combos/{combo_id}/`
- **Action**: `{store_slug}/cart/add-combo/`

---

## Endpoint Routes

### Public Storefront Routes

```
GET    /api/v1/stores/{store_slug}/combos/              → ComboListView
GET    /api/v1/stores/{store_slug}/combos/{combo_id}/   → ComboDetailView
POST   /api/v1/stores/{store_slug}/cart/add-combo/      → AddComboToCartView
```

### Legacy Routes (Backward Compatibility)

```
GET    /api/v1/stores/s/{store_slug}/combos/            → ComboListView
GET    /api/v1/stores/s/{store_slug}/combos/{combo_id}/ → ComboDetailView
POST   /api/v1/stores/s/{store_slug}/cart/add-combo/    → AddComboToCartView
```

---

## Route Registration in Code

**File**: `/home/graco/WORK/server2/apps/stores/urls.py`

### Step 1: Imports (Lines 12-34)

```python
from .api.views import (
    # ... other imports ...
    # Combo views
    ComboDetailView, ComboListView, AddComboToCartView,
)
```

### Step 2: Pattern Definition (Lines 163-228)

```python
store_frontend_patterns = [
    path('', StorePublicView.as_view(), name='store-public'),
    path('app-config/', StoreAppConfigView.as_view(), name='store-app-config'),
    path('catalog/', StoreCatalogView.as_view(), name='store-catalog'),
    path('customer/profile/', StoreCustomerProfileView.as_view(), name='store-customer-profile'),
    
    # Combo endpoints
    path('combos/', ComboListView.as_view(), name='combo-list'),
    path('combos/<uuid:combo_id>/', ComboDetailView.as_view(), name='combo-detail'),
    
    # Cart endpoints
    path('cart/', StoreCartViewSet.as_view({'get': 'get_cart_by_store'}), name='store-cart'),
    path('cart/add/', StoreCartViewSet.as_view({'post': 'add_item'}), name='store-cart-add'),
    path('cart/add-combo/', AddComboToCartView.as_view(), name='add-combo-to-cart'),
    
    # ... other patterns ...
]
```

### Step 3: URL Inclusion (Lines 231-328)

```python
urlpatterns = [
    # ==========================================================================
    # ADMIN/MANAGEMENT ENDPOINTS (require auth)
    # ==========================================================================
    path('', include(router.urls)),
    path('', include(stores_router.urls)),
    path('', include(products_router.urls)),
    
    # ... other patterns ...
    
    # ==========================================================================
    # PUBLIC STOREFRONT ENDPOINTS (by store slug)
    # Base: /api/v1/stores/{store_slug}/
    # Keep these last so catch-all slug routes do not shadow global endpoints.
    # ==========================================================================

    # Legacy alias kept for backwards compatibility with older frontends
    path('s/<slug:store_slug>/', include(store_frontend_patterns)),
    # Store-specific storefront endpoints (canonical)
    path('<slug:store_slug>/', include(store_frontend_patterns)),
]
```

---

## URL Pattern Matching Examples

### Example 1: List Combos (Canonical)

```
Request: GET /api/v1/stores/ce-saladas/combos/
Route Match: path('<slug:store_slug>/', include(store_frontend_patterns))
             └─ path('combos/', ComboListView.as_view(), name='combo-list')

View: ComboListView
Parameters: store_slug='ce-saladas'
Handler: ComboListView.get(request, store_slug='ce-saladas')
```

### Example 2: Get Combo Detail (Canonical)

```
Request: GET /api/v1/stores/ce-saladas/combos/c6e942b2-13a5-49aa-a47d-5ba19d0c8f19/
Route Match: path('<slug:store_slug>/', include(store_frontend_patterns))
             └─ path('combos/<uuid:combo_id>/', ComboDetailView.as_view(), name='combo-detail')

View: ComboDetailView
Parameters: store_slug='ce-saladas', combo_id='c6e942b2-13a5-49aa-a47d-5ba19d0c8f19'
Handler: ComboDetailView.get(request, store_slug='ce-saladas', combo_id=UUID(...))
```

### Example 3: Add Combo to Cart (Canonical)

```
Request: POST /api/v1/stores/ce-saladas/cart/add-combo/
Route Match: path('<slug:store_slug>/', include(store_frontend_patterns))
             └─ path('cart/add-combo/', AddComboToCartView.as_view(), name='add-combo-to-cart')

View: AddComboToCartView
Parameters: store_slug='ce-saladas'
Handler: AddComboToCartView.post(request, store_slug='ce-saladas')
```

### Example 4: List Combos (Legacy)

```
Request: GET /api/v1/stores/s/ce-saladas/combos/
Route Match: path('s/<slug:store_slug>/', include(store_frontend_patterns))
             └─ path('combos/', ComboListView.as_view(), name='combo-list')

View: ComboListView
Parameters: store_slug='ce-saladas'
Handler: ComboListView.get(request, store_slug='ce-saladas')
Note: Same handler as canonical route, backward compatible
```

---

## Django URL Dispatcher Flow

```
Request URL: /api/v1/stores/ce-saladas/combos/
                │
                ├─ config/urls.py:80
                │  path('stores/', include('apps.stores.urls'))
                │  ✓ Matches 'stores/'
                │
                ├─ apps/stores/urls.py:327
                │  path('<slug:store_slug>/', include(store_frontend_patterns))
                │  ✓ Matches 'ce-saladas/' (slug validator)
                │
                └─ store_frontend_patterns[169]
                   path('combos/', ComboListView.as_view(), name='combo-list')
                   ✓ Matches 'combos/'
                   
                   → ComboListView.get(request, store_slug='ce-saladas')
```

---

## URL Reverse Lookup

Django allows generating URLs using the `reverse()` function with endpoint names:

### Python / Django Templates

```python
from django.urls import reverse

# Get canonical list URL
url = reverse('stores:combo-list', kwargs={'store_slug': 'ce-saladas'})
# Result: /api/v1/stores/ce-saladas/combos/

# Get detail URL
url = reverse('stores:combo-detail', kwargs={
    'store_slug': 'ce-saladas',
    'combo_id': 'c6e942b2-13a5-49aa-a47d-5ba19d0c8f19'
})
# Result: /api/v1/stores/ce-saladas/combos/c6e942b2-13a5-49aa-a47d-5ba19d0c8f19/

# Get add-to-cart URL
url = reverse('stores:add-combo-to-cart', kwargs={'store_slug': 'ce-saladas'})
# Result: /api/v1/stores/ce-saladas/cart/add-combo/
```

### Template Syntax

```html
<a href="{% url 'stores:combo-list' store_slug='ce-saladas' %}">View Combos</a>
<a href="{% url 'stores:combo-detail' store_slug='ce-saladas' combo_id=combo.id %}">View Details</a>
```

---

## Namespace Configuration

```python
# apps/stores/urls.py:229
app_name = 'stores'

# Fully qualified name: stores:combo-list
# Used in reverse(): reverse('stores:combo-list', ...)
```

---

## Route Priority & Order

The URL patterns are evaluated in order. Important:

1. **Admin/Management patterns** (lines 235-237): Exact paths like `/combos/`, `/products/`
2. **Global patterns** (lines 239-310): Payment, webhooks, print, etc.
3. **Store-specific patterns** (lines 325-327): `/{store_slug}/` (LAST)

**Why last?** The store slug catchall (`<slug:store_slug>/`) would match many paths prematurely. By placing it last, we ensure admin endpoints like `/combos/` are matched first.

```
Request: GET /api/v1/stores/combos/
                           ↓
         Does NOT match store_slug pattern
         (would need a store slug like 'combos')
                           ↓
         Matches admin router pattern
         → StoreComboViewSet (admin/management)

Request: GET /api/v1/stores/ce-saladas/combos/
                           ↓
         Matches store_slug pattern
                           ↓
         Matches store_frontend_patterns
         → ComboListView (public)
```

---

## Pattern Validation & Constraints

### Store Slug Pattern

```python
path('<slug:store_slug>/', include(store_frontend_patterns))
```

**Validator**: Django's `SlugField` regex
- Allows: lowercase letters, numbers, hyphens
- Pattern: `^[-a-z0-9]+$`
- Examples:
  - ✅ `ce-saladas`
  - ✅ `kero-kero`
  - ✅ `pastita`
  - ❌ `Cê Saladas` (uppercase, special chars)
  - ❌ `ce_saladas` (underscores not allowed)

### Combo ID Pattern

```python
path('combos/<uuid:combo_id>/', ComboDetailView.as_view(), ...)
```

**Validator**: Django's `UUIDField` converter
- Format: UUID v4
- Pattern: `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
- Examples:
  - ✅ `c6e942b2-13a5-49aa-a47d-5ba19d0c8f19`
  - ❌ `c6e942b2-13a5-49aa-a47d` (incomplete)
  - ❌ `not-a-uuid`

---

## Query Parameter Handling

Query parameters are NOT part of the URL pattern matching. They're handled in views:

```
Request: GET /api/v1/stores/ce-saladas/combos/?is_active=true&page=2

URL Match: path('combos/', ComboListView.as_view(), ...)
Query Params: Extracted in view as request.query_params
```

**View Implementation** (combo_views.py:108-111):

```python
def get(self, request, store_slug):
    # Query params extracted here
    is_active = request.query_params.get('is_active')
    if is_active is not None:
        is_active_bool = is_active.lower() in ['true', '1', 'yes']
        queryset = queryset.filter(is_active=is_active_bool)
```

---

## Content Negotiation

URL patterns don't handle content types directly. DRF uses the `Accept` header:

```
Request:
GET /api/v1/stores/ce-saladas/combos/ HTTP/1.1
Accept: application/json

Response:
HTTP/1.1 200 OK
Content-Type: application/json
```

Supported formats via format suffix:
- `.json` - Explicit JSON (if enabled in settings)
- `.xml` - XML (if renderer registered)

**Note**: All Pastita endpoints use JSON by default.

---

## URL Edge Cases & Gotchas

### Issue 1: Store Slug vs. Endpoint Name Collision

**Problem**: If store slug is `combos`, URL becomes `/api/v1/stores/combos/combos/`

```
Request: GET /api/v1/stores/combos/combos/

Matching:
  path('<slug:store_slug>/', ...)  ← slug='combos'
  path('combos/', ComboListView.as_view(), ...)  ← 'combos/' within patterns
  
Result: ComboListView for store with slug='combos'
```

**Solution**: Avoid store slugs matching internal endpoint names

### Issue 2: UUID Not Starting with Digit

**Problem**: Some UUID generators might produce UUIDs starting with non-digits

```
UUID: 00000000-0000-0000-0000-000000000000
Pattern: Django's uuid converter accepts all valid UUIDs
Result: ✅ Works correctly
```

### Issue 3: Trailing Slashes

Django enforces trailing slash consistency:

```
✅ GET /api/v1/stores/ce-saladas/combos/
❌ GET /api/v1/stores/ce-saladas/combos   (no trailing slash)
→ 301 Redirect to URL with trailing slash
```

To allow both, add `path()` without trailing slash:
```python
path('combos', ComboListView.as_view(), ...),  # Allow both
path('combos/', ComboListView.as_view(), ...),
```

---

## Testing URL Routing

### Test 1: Check Route Registration

```bash
python manage.py show_urls | grep combo
```

Expected output:
```
combos/                                    stores.views.ComboListView
combos/<uuid:combo_id>/                    stores.views.ComboDetailView
cart/add-combo/                            stores.views.AddComboToCartView
```

### Test 2: Reverse URL Generation

```python
from django.urls import reverse

url = reverse('stores:combo-list', kwargs={'store_slug': 'ce-saladas'})
print(url)  # /api/v1/stores/ce-saladas/combos/
```

### Test 3: HTTP Request

```bash
curl http://localhost:8001/api/v1/stores/ce-saladas/combos/ -v
```

---

## URL Configuration Best Practices

1. **Keep Store Pattern Last**: Prevents catchall from shadowing specific endpoints
2. **Use Named URLs**: Makes refactoring easier (`reverse('stores:combo-list', ...)`)
3. **Validate Slugs**: Only allow safe characters (slug validator does this)
4. **Document URLs**: Keep this documentation updated with routes
5. **Test URL Resolution**: Write tests for URL patterns
6. **Use Type Converters**: UUID, int, slug validators catch errors early
7. **Namespace Isolation**: Use `app_name = 'stores'` for clarity

---

## Related URLs

### Admin/Management URLs
```
GET    /api/v1/combos/                    → StoreComboViewSet (filtered by store)
POST   /api/v1/combos/                    → Create combo
PATCH  /api/v1/combos/{id}/               → Update combo
DELETE /api/v1/combos/{id}/               → Delete combo
```

### Admin with Store
```
GET    /api/v1/stores/ce-saladas/combos/  → Nested routers (if configured)
```

### Related Storefront URLs
```
GET    /api/v1/stores/ce-saladas/         → Store detail (public)
GET    /api/v1/stores/ce-saladas/catalog/ → Full catalog (includes combos)
GET    /api/v1/stores/ce-saladas/cart/    → User's cart
POST   /api/v1/stores/ce-saladas/cart/add-combo/ → Add to cart
```

---

## URL Configuration File Structure

```
config/
├── urls.py                 ← Main URL config (includes stores/)
└── settings/
    ├── base.py            ← ROOT_URLCONF = 'config.urls'
    └── ...

apps/stores/
├── urls.py                ← Store-specific routes + combo routes
├── api/
│   ├── views/
│   │   └── combo_views.py ← View implementations
│   └── ...
└── ...
```

---

## Changelog

**2026-06-06**: Initial URL routing documentation
- ✅ Canonical and legacy routes documented
- ✅ URL pattern matching flow explained
- ✅ Edge cases and best practices included

