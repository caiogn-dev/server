# Combo API Endpoints Documentation

**Status**: ✅ Routes fully implemented in `/apps/stores/urls.py` and `/apps/stores/api/views/combo_views.py`

**Base Path**: `/api/v1/stores/{store_slug}/combos/`

## Overview

The Combo API provides public endpoints for listing and retrieving combo details, along with cart integration for adding combos to customer carts. All combo endpoints enforce tenant isolation using the `store_slug` parameter.

### Architectural Notes

- **Tenant Isolation**: All routes validate that combos belong to the requested store
- **Authentication**: Public endpoints use `AllowAny` permissions (no auth required)
- **Cart Integration**: AddComboToCartView supports both authenticated users and session-based guest carts
- **Pagination**: List endpoint supports configurable page sizes (default: 20, max: 100)

---

## Endpoints

### 1. List Combos

**Route**: `GET /api/v1/stores/{store_slug}/combos/`

**Purpose**: List all active combos for a store with optional filtering and pagination

**Name**: `combo-list`

**Authentication**: Not required

**URL Pattern**:
```
GET /api/v1/stores/ce-saladas/combos/?is_active=true&page=1&page_size=20
```

**Query Parameters**:
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `is_active` | bool string | (no filter) | N/A | Filter by active status: `true`, `false` |
| `page` | int | 1 | N/A | Page number for pagination |
| `page_size` | int | 20 | 100 | Results per page |

**Success Response** (200 OK):
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "c6e942b2-13a5-49aa-a47d-5ba19d0c8f19",
      "store": "aa0a63dd-7feb-4556-be63-66b98fe88361",
      "name": "Test Combo 1",
      "slug": "test-combo-1",
      "description": "Test combo description",
      "image": null,
      "image_url": "",
      "price": "50.00",
      "is_active": true,
      "sort_order": 0,
      "metadata": {},
      "created_at": "2026-06-06T16:55:50.123456+00:00",
      "updated_at": "2026-06-06T16:55:50.123456+00:00"
    }
  ]
}
```

**Error Responses**:
- `404 Not Found`: Store slug does not exist
  ```json
  {
    "detail": "Loja não encontrada."
  }
  ```

---

### 2. Get Combo Details

**Route**: `GET /api/v1/stores/{store_slug}/combos/{combo_id}/`

**Purpose**: Retrieve full combo details including groups, variants, selection rules, and per-variant limits

**Name**: `combo-detail`

**Authentication**: Not required

**URL Pattern**:
```
GET /api/v1/stores/ce-saladas/combos/c6e942b2-13a5-49aa-a47d-5ba19d0c8f19/
```

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `combo_id` | UUID | Combo ID (UUID v4 format) |

**Success Response** (200 OK):
```json
{
  "id": "c6e942b2-13a5-49aa-a47d-5ba19d0c8f19",
  "store": "aa0a63dd-7feb-4556-be63-66b98fe88361",
  "name": "Test Combo 1",
  "slug": "test-combo-1",
  "description": "Test combo description",
  "image": null,
  "image_url": "",
  "price": "50.00",
  "is_active": true,
  "sort_order": 0,
  "groups": [
    {
      "id": "group-uuid-1",
      "name": "Main Protein",
      "description": "Choose your main protein",
      "selection_type": "single",
      "min_selections": 1,
      "max_selections": 1,
      "variants": [
        {
          "id": "variant-uuid-1",
          "product_id": "product-uuid-1",
          "product_name": "Chicken Breast",
          "price_modifier": "0.00",
          "stock": 100,
          "is_in_stock": true,
          "max_quantity": 1
        }
      ]
    }
  ],
  "metadata": {},
  "created_at": "2026-06-06T16:55:50.123456+00:00",
  "updated_at": "2026-06-06T16:55:50.123456+00:00"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid combo_id format
  ```json
  {
    "detail": "ID de combo inválido."
  }
  ```
- `404 Not Found`: Store slug or combo ID not found
  ```json
  {
    "detail": "Loja não encontrada."
  }
  ```
  or
  ```json
  {
    "detail": "Combo não encontrado."
  }
  ```

---

### 3. Add Combo to Cart

**Route**: `POST /api/v1/stores/{store_slug}/cart/add-combo/`

**Purpose**: Add a combo with validated variant selections to the customer's cart

**Name**: `add-combo-to-cart`

**Authentication**: Not required (supports both authenticated users and guest sessions)

**URL Pattern**:
```
POST /api/v1/stores/ce-saladas/cart/add-combo/
```

**Request Body**:
```json
{
  "combo_id": "c6e942b2-13a5-49aa-a47d-5ba19d0c8f19",
  "quantity": 1,
  "selections": {
    "group-uuid-1": ["variant-uuid-1"],
    "group-uuid-2": ["variant-uuid-2", "variant-uuid-3"]
  }
}
```

**Request Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `combo_id` | UUID | Yes | Combo ID to add |
| `quantity` | int | No (default: 1) | Quantity of combos to add (must be ≥ 1) |
| `selections` | object | No (default: {}) | Variant selections per group (group_id → list of variant_ids) |

**Success Response** (200 OK):
```json
{
  "cart_id": "cart-uuid",
  "store_id": "aa0a63dd-7feb-4556-be63-66b98fe88361",
  "item_count": 1,
  "subtotal": "50.00",
  "items": [
    {
      "id": "cart-item-uuid",
      "combo_name": "Test Combo 1",
      "quantity": 1,
      "unit_price": "50.00",
      "subtotal": "50.00",
      "selections": {
        "group-uuid-1": ["variant-uuid-1"]
      }
    }
  ]
}
```

**Error Responses**:
- `400 Bad Request`: Validation error
  ```json
  {
    "detail": "combo_id é obrigatório."
  }
  ```
  or
  ```json
  {
    "detail": "ID de combo inválido."
  }
  ```
  or
  ```json
  {
    "detail": "Quantidade deve ser um número inteiro positivo."
  }
  ```
  or
  ```json
  {
    "errors": {
      "group_uuid_1": ["Missing required variant selection"],
      "group_uuid_2": ["Too many variants selected"]
    }
  }
  ```

- `404 Not Found`: Store or combo not found
  ```json
  {
    "detail": "Loja não encontrada."
  }
  ```
  or
  ```json
  {
    "detail": "Combo não encontrado."
  }
  ```

- `500 Internal Server Error`: Cart creation error
  ```json
  {
    "detail": "Erro ao adicionar combo ao carrinho: <error message>"
  }
  ```

**Cart Management**:
- **Authenticated Users**: Uses `StoreCart` scoped to `store + user + is_active=True`
- **Guest Customers**: Uses `StoreCart` scoped to `store + session_key + user=null + is_active=True`
- **Session Creation**: If no session exists, one is created automatically

---

## Implementation Details

### File Locations

```
apps/stores/
├── api/
│   ├── views/
│   │   └── combo_views.py          ✅ View classes (ComboListView, ComboDetailView, AddComboToCartView)
│   ├── combo_serializers.py        ✅ Serializers (ComboListSerializer, ComboDetailSerializer)
│   └── ...
├── models/
│   ├── combo_group.py              ✅ ComboGroup, ComboGroupVariant models
│   ├── product.py                  ✅ StoreCombo model
│   └── ...
├── validators.py                   ✅ ComboSelectionValidator
├── urls.py                         ✅ Route registration (store_frontend_patterns)
└── ...
```

### URL Configuration

The combo endpoints are registered in `apps/stores/urls.py` within the `store_frontend_patterns` list (lines 169-173):

```python
store_frontend_patterns = [
    # ... other patterns ...
    # Combo endpoints
    path('combos/', ComboListView.as_view(), name='combo-list'),
    path('combos/<uuid:combo_id>/', ComboDetailView.as_view(), name='combo-detail'),
    # ... cart endpoints ...
    path('cart/add-combo/', AddComboToCartView.as_view(), name='add-combo-to-cart'),
]
```

These patterns are included twice for backwards compatibility:
```python
urlpatterns = [
    # ... admin patterns ...
    # Legacy alias kept for backwards compatibility with older frontends
    path('s/<slug:store_slug>/', include(store_frontend_patterns)),
    # Store-specific storefront endpoints (canonical)
    path('<slug:store_slug>/', include(store_frontend_patterns)),
]
```

This provides two access patterns:
- **Canonical**: `/api/v1/stores/ce-saladas/combos/`
- **Legacy**: `/api/v1/stores/s/ce-saladas/combos/` (backward compatibility)

### View Classes

#### ComboListView (APIView)

- **Method**: GET
- **Permissions**: AllowAny
- **Features**:
  - Filters by `is_active` query parameter
  - Supports pagination (ComboPagination: 20 items/page, max 100)
  - Orders by `sort_order` and `name`
  - Returns `ComboListSerializer`

#### ComboDetailView (APIView)

- **Method**: GET
- **Permissions**: AllowAny
- **Features**:
  - UUID validation for `combo_id`
  - Store tenant isolation
  - Returns `ComboDetailSerializer` with full group and variant data

#### AddComboToCartView (APIView)

- **Method**: POST
- **Permissions**: AllowAny
- **Features**:
  - Atomic transaction support
  - Request validation (combo_id, quantity, selections)
  - ComboSelectionValidator integration
  - Automatic session management for guest users
  - Returns cart summary

### Serializers

#### ComboListSerializer

Used by `ComboListView` to serialize combo list responses. Fields:
- `id`, `store`, `name`, `slug`, `description`
- `image`, `image_url`, `price`, `is_active`
- `sort_order`, `metadata`, `created_at`, `updated_at`

#### ComboDetailSerializer

Used by `ComboDetailView` to serialize detailed combo responses. Fields:
- All fields from ComboListSerializer
- `groups`: Nested group data with variants and selection rules
- Variant stock info and per-variant selection limits

### Validation

#### ComboSelectionValidator

Validates variant selections per combo. Checks:
1. Required selections per group (min_selections)
2. Selection limits per group (max_selections)
3. Per-variant quantity limits
4. Stock availability (if tracked)

Location: `apps/stores/validators.py`

---

## Testing the Endpoints

### Test 1: List Combos (No Parameters)

```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/"
```

### Test 2: List Combos (Filter by Active)

```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/?is_active=true&page_size=10"
```

### Test 3: Get Combo Detail

```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/c6e942b2-13a5-49aa-a47d-5ba19d0c8f19/"
```

### Test 4: Add Combo to Cart (Authenticated)

```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Authorization: Token YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "c6e942b2-13a5-49aa-a47d-5ba19d0c8f19",
    "quantity": 2,
    "selections": {
      "group-uuid-1": ["variant-uuid-1"],
      "group-uuid-2": ["variant-uuid-2"]
    }
  }'
```

### Test 5: Add Combo to Cart (Guest)

```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "c6e942b2-13a5-49aa-a47d-5ba19d0c8f19",
    "quantity": 1,
    "selections": {
      "group-uuid-1": ["variant-uuid-1"]
    }
  }'
```

---

## Integration with Storefront

### Frontend Contract

Frontends (pastita-3d, ce-saladas-flutter) can use these endpoints directly:

```javascript
// React/Next.js example
import axios from 'axios';

const API_BASE = 'https://backend.pastita.com.br/api/v1';
const STORE_SLUG = 'ce-saladas';

// List combos
async function listCombos(filters = {}) {
  const response = await axios.get(
    `${API_BASE}/stores/${STORE_SLUG}/combos/`,
    { params: filters }
  );
  return response.data.results;
}

// Get combo details
async function getComboDetails(comboId) {
  const response = await axios.get(
    `${API_BASE}/stores/${STORE_SLUG}/combos/${comboId}/`
  );
  return response.data;
}

// Add to cart
async function addComboToCart(comboId, quantity, selections) {
  const response = await axios.post(
    `${API_BASE}/stores/${STORE_SLUG}/cart/add-combo/`,
    { combo_id: comboId, quantity, selections }
  );
  return response.data;
}
```

---

## Database Models

### StoreCombo

```python
class StoreCombo(models.Model):
    store = ForeignKey(Store, ...)
    name = CharField(max_length=255)
    slug = SlugField()
    description = TextField()
    price = DecimalField()
    image = ForeignKey(StoreImage, null=True, blank=True)
    is_active = BooleanField(default=True)
    sort_order = IntegerField(default=0)
    metadata = JSONField(default=dict)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

### ComboGroup

```python
class ComboGroup(models.Model):
    combo = ForeignKey(StoreCombo, ...)
    name = CharField(max_length=255)
    description = TextField()
    selection_type = CharField(choices=['single', 'multiple'])
    min_selections = IntegerField(default=1)
    max_selections = IntegerField(default=1)
    sort_order = IntegerField(default=0)
    is_required = BooleanField(default=True)
    metadata = JSONField(default=dict)
```

### ComboGroupVariant

```python
class ComboGroupVariant(models.Model):
    group = ForeignKey(ComboGroup, ...)
    product = ForeignKey(StoreProduct, ...)
    price_modifier = DecimalField(default=0)
    stock = IntegerField()
    max_quantity = IntegerField(default=1)
    sort_order = IntegerField(default=0)
    is_available = BooleanField(default=True)
```

---

## API Response Contracts

### Pagination Contract

All list endpoints follow DRF pagination format:

```json
{
  "count": 100,
  "next": "http://api.example.com/stores/ce-saladas/combos/?page=2",
  "previous": null,
  "results": [...]
}
```

### Error Response Contract

All error responses follow a consistent format:

```json
{
  "detail": "User-friendly error message in Portuguese"
}
```

Validation errors return:

```json
{
  "errors": {
    "field_name": ["Error message 1", "Error message 2"]
  }
}
```

---

## Performance Considerations

1. **Query Optimization**:
   - `ComboListView` uses `order_by('sort_order', 'name')`
   - `ComboDetailView` uses `select_related()` for store
   - Consider adding `.prefetch_related('groups__variants')` for detail view

2. **Pagination**:
   - Default: 20 items/page
   - Max: 100 items/page
   - Prevents excessive data transfer

3. **Caching Opportunities**:
   - List endpoint can be cached per store (30-60 seconds)
   - Detail endpoint can be cached per combo (same duration)
   - Cache invalidation on combo save

---

## Related Endpoints

- **Catalog**: `GET /api/v1/stores/{store_slug}/catalog/` (includes combos_destaque)
- **Cart Management**: `GET/POST/PATCH/DELETE /api/v1/stores/{store_slug}/cart/`
- **Checkout**: `POST /api/v1/stores/{store_slug}/checkout/`
- **Admin Combos**: `GET/POST /api/combos/` (requires auth)

---

## Future Enhancements

1. **Filtering & Search**:
   - Add `search` query parameter for full-text search
   - Add `category` filter for combo grouping
   - Add `price_range` filter

2. **Optimization**:
   - Add `select_for_update()` to avoid race conditions in AddComboToCartView
   - Implement Redis caching for frequently accessed combos
   - Add database indexes on `store_id`, `is_active`, `sort_order`

3. **Features**:
   - Bulk add to cart (`POST /carts/add-items/`)
   - Combo recommendations (similar combos, frequently paired items)
   - Combo pricing variations (time-based discounts, loyalty pricing)

---

## Changelog

- **2026-06-06**: Initial documentation
  - ComboListView: GET /combos/
  - ComboDetailView: GET /combos/{combo_id}/
  - AddComboToCartView: POST /cart/add-combo/
  - Full tenant isolation and validation

