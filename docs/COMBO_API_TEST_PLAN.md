# Combo API Endpoints - Test Plan

**Status**: Ready for Testing  
**Last Updated**: 2026-06-06  
**Test Environment**: Docker + PostgreSQL + Redis

---

## Prerequisites

1. **Docker Containers Running**:
   ```bash
   docker ps | grep pastita_web pastita_nginx
   ```

2. **Test Database Seeded**:
   ```bash
   docker exec pastita_web python manage.py loaddata stores
   ```

3. **Sample Data Created**:
   - Store: `ce-saladas` (slug: ce-saladas)
   - Products with combos enabled

---

## Test Cases

### TEST SUITE 1: LIST COMBOS (ComboListView)

#### Test 1.1: List All Combos (No Filters)

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/`

**Expected**: 200 OK with paginated results

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/" \
  -H "Content-Type: application/json"
```

**Expected Response Structure**:
```json
{
  "count": <integer>,
  "next": <string|null>,
  "previous": <string|null>,
  "results": [
    {
      "id": "<uuid>",
      "store": "<uuid>",
      "name": "<string>",
      "slug": "<string>",
      "description": "<string>",
      "image": "<uuid|null>",
      "image_url": "<string>",
      "price": "<decimal>",
      "is_active": <boolean>,
      "sort_order": <integer>,
      "metadata": <object>,
      "created_at": "<iso8601>",
      "updated_at": "<iso8601>"
    }
  ]
}
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] Response is valid JSON
- [ ] `results` is a list
- [ ] Each item has required fields
- [ ] Pagination metadata present

---

#### Test 1.2: Filter by is_active=true

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/?is_active=true`

**Expected**: 200 OK with only active combos

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/?is_active=true" \
  -H "Content-Type: application/json"
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] All items in `results` have `is_active: true`
- [ ] No inactive combos are included

---

#### Test 1.3: Filter by is_active=false

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/?is_active=false`

**Expected**: 200 OK with only inactive combos (or empty if none)

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/?is_active=false" \
  -H "Content-Type: application/json"
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] All items in `results` have `is_active: false`
- [ ] No active combos are included

---

#### Test 1.4: Pagination - Page 1 with Custom Page Size

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/?page=1&page_size=5`

**Expected**: 200 OK with up to 5 results

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/?page=1&page_size=5" \
  -H "Content-Type: application/json" | jq '.'
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] Number of items in `results` ≤ 5
- [ ] `count` field shows total available items
- [ ] `next` field is populated if more pages exist

---

#### Test 1.5: Pagination - Beyond Max Page Size

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/?page_size=200`

**Expected**: 200 OK with max 100 items (limit enforced)

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/?page_size=200" \
  -H "Content-Type: application/json" | jq '.results | length'
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] Number of items ≤ 100 (max enforced)
- [ ] No error returned (graceful limit)

---

#### Test 1.6: Non-Existent Store

**Endpoint**: `GET /api/v1/stores/non-existent-store/combos/`

**Expected**: 404 Not Found

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/non-existent-store/combos/" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "detail": "Loja não encontrada."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 404
- [ ] Error message is "Loja não encontrada."

---

### TEST SUITE 2: GET COMBO DETAILS (ComboDetailView)

#### Test 2.1: Get Valid Combo Details

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/{combo_id}/`

**Prerequisites**:
1. Get a valid combo_id from Test 1.1
2. Use that ID in the URL

**Command**:
```bash
COMBO_ID="<from_test_1.1>"
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/${COMBO_ID}/" \
  -H "Content-Type: application/json" | jq '.'
```

**Expected Response Structure**:
```json
{
  "id": "<uuid>",
  "store": "<uuid>",
  "name": "<string>",
  "slug": "<string>",
  "description": "<string>",
  "image": "<uuid|null>",
  "image_url": "<string>",
  "price": "<decimal>",
  "is_active": <boolean>,
  "sort_order": <integer>,
  "groups": [
    {
      "id": "<uuid>",
      "name": "<string>",
      "description": "<string>",
      "selection_type": "<single|multiple>",
      "min_selections": <integer>,
      "max_selections": <integer>,
      "variants": [
        {
          "id": "<uuid>",
          "product_id": "<uuid>",
          "product_name": "<string>",
          "price_modifier": "<decimal>",
          "stock": <integer>,
          "is_in_stock": <boolean>,
          "max_quantity": <integer>
        }
      ]
    }
  ],
  "metadata": <object>,
  "created_at": "<iso8601>",
  "updated_at": "<iso8601>"
}
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] Response has `groups` array
- [ ] Each group has `variants` array
- [ ] All required fields present

---

#### Test 2.2: Get Combo with Invalid UUID Format

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/invalid-id/`

**Expected**: 400 Bad Request

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/invalid-id/" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "detail": "ID de combo inválido."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Error message is "ID de combo inválido."

---

#### Test 2.3: Get Non-Existent Combo (Valid UUID, Wrong Store)

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/00000000-0000-0000-0000-000000000000/`

**Expected**: 404 Not Found

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/00000000-0000-0000-0000-000000000000/" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "detail": "Combo não encontrado."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 404
- [ ] Error message is "Combo não encontrado."

---

#### Test 2.4: Get Combo from Non-Existent Store

**Endpoint**: `GET /api/v1/stores/invalid-store/combos/{combo_id}/`

**Expected**: 404 Not Found

**Command**:
```bash
COMBO_ID="<from_test_2.1>"
curl -X GET "http://localhost:8001/api/v1/stores/invalid-store/combos/${COMBO_ID}/" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "detail": "Loja não encontrada."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 404
- [ ] Error message is "Loja não encontrada."

---

#### Test 2.5: Tenant Isolation - Combo from Different Store

**Prerequisites**:
1. Get combo_id from `kero-kero` store
2. Try to access it from `ce-saladas` store

**Expected**: 404 Not Found (tenant isolation enforced)

**Command**:
```bash
# Get combo from kero-kero
KERO_COMBO=$(curl -s "http://localhost:8001/api/v1/stores/kero-kero/combos/" | jq -r '.results[0].id // empty')

# Try to access from ce-saladas
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/${KERO_COMBO}/" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "detail": "Combo não encontrado."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 404
- [ ] Combo isolation enforced (no cross-store access)

---

### TEST SUITE 3: ADD COMBO TO CART (AddComboToCartView)

#### Test 3.1: Add Valid Combo to Cart (Guest User)

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Prerequisites**:
1. Get a valid combo_id from Test 1.1
2. Get group and variant IDs from Test 2.1

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id>",
    "quantity": 1,
    "selections": {
      "<group_id>": ["<variant_id>"]
    }
  }' | jq '.'
```

**Expected Response**:
```json
{
  "cart_id": "<uuid>",
  "store_id": "<uuid>",
  "item_count": 1,
  "subtotal": "<decimal>",
  "items": [
    {
      "id": "<uuid>",
      "combo_name": "<string>",
      "quantity": 1,
      "unit_price": "<decimal>",
      "subtotal": "<decimal>",
      "selections": {
        "<group_id>": ["<variant_id>"]
      }
    }
  ]
}
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] `cart_id` is returned
- [ ] `item_count` = 1
- [ ] `subtotal` matches expected price
- [ ] Selections are preserved in response

---

#### Test 3.2: Add Combo with Multiple Quantities

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id>",
    "quantity": 5,
    "selections": {
      "<group_id>": ["<variant_id>"]
    }
  }' | jq '.items[0] | {quantity, subtotal}'
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] `quantity` = 5
- [ ] `subtotal` = unit_price × 5

---

#### Test 3.3: Missing combo_id

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Expected**: 400 Bad Request

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "quantity": 1,
    "selections": {}
  }'
```

**Expected Response**:
```json
{
  "detail": "combo_id é obrigatório."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Error message is "combo_id é obrigatório."

---

#### Test 3.4: Invalid combo_id Format

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Expected**: 400 Bad Request

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "not-a-uuid",
    "quantity": 1,
    "selections": {}
  }'
```

**Expected Response**:
```json
{
  "detail": "ID de combo inválido."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Error message is "ID de combo inválido."

---

#### Test 3.5: Invalid Quantity (Non-Integer)

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Expected**: 400 Bad Request

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id>",
    "quantity": "abc",
    "selections": {}
  }'
```

**Expected Response**:
```json
{
  "detail": "Quantidade deve ser um número inteiro positivo."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Error message mentions quantity validation

---

#### Test 3.6: Invalid Quantity (Negative)

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Expected**: 400 Bad Request

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id>",
    "quantity": -1,
    "selections": {}
  }'
```

**Expected Response**:
```json
{
  "detail": "Quantidade deve ser um número inteiro positivo."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Rejects zero and negative quantities

---

#### Test 3.7: Non-Existent Combo

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Expected**: 404 Not Found

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "00000000-0000-0000-0000-000000000000",
    "quantity": 1,
    "selections": {}
  }'
```

**Expected Response**:
```json
{
  "detail": "Combo não encontrado."
}
```

**Pass Criteria**:
- [ ] HTTP Status: 404

---

#### Test 3.8: Missing Required Selection

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Prerequisites**:
- Combo has group with `min_selections=1` (required)

**Expected**: 400 Bad Request with validation error

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id>",
    "quantity": 1,
    "selections": {}
  }'
```

**Expected Response**:
```json
{
  "errors": {
    "<group_id>": ["Missing required variant selection"]
  }
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Errors object contains validation messages
- [ ] Missing group is identified

---

#### Test 3.9: Too Many Selections

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Prerequisites**:
- Combo has group with `max_selections=1` but we send 2 variants

**Expected**: 400 Bad Request with validation error

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id>",
    "quantity": 1,
    "selections": {
      "<group_id>": ["<variant_id_1>", "<variant_id_2>"]
    }
  }'
```

**Expected Response**:
```json
{
  "errors": {
    "<group_id>": ["Too many variants selected"]
  }
}
```

**Pass Criteria**:
- [ ] HTTP Status: 400
- [ ] Selection limit enforced

---

#### Test 3.10: Add Multiple Combos to Cart (Sequential)

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/` (called twice)

**Expected**: Both items in cart, item_count=2

**Command**:
```bash
# First add
CART_ID=$(curl -s -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id_1>",
    "quantity": 1,
    "selections": {"<group_id>": ["<variant_id>"]}
  }' | jq -r '.cart_id')

# Second add
curl -s -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: application/json" \
  -d '{
    "combo_id": "<combo_id_2>",
    "quantity": 1,
    "selections": {"<group_id>": ["<variant_id>"]}
  }' | jq '.item_count'
```

**Pass Criteria**:
- [ ] First request returns cart_id
- [ ] Second request returns same cart_id
- [ ] `item_count` = 2
- [ ] Both combos in items array

---

### TEST SUITE 4: URL PATTERN VERIFICATION

#### Test 4.1: Canonical URL Pattern

**Pattern**: `/api/v1/stores/{store_slug}/combos/`

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/" \
  -H "Content-Type: application/json" | jq '.count'
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] Response is valid

---

#### Test 4.2: Legacy URL Pattern (Backward Compatibility)

**Pattern**: `/api/v1/stores/s/{store_slug}/combos/`

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/s/ce-saladas/combos/" \
  -H "Content-Type: application/json" | jq '.count'
```

**Pass Criteria**:
- [ ] HTTP Status: 200
- [ ] Response is valid (legacy route works)
- [ ] Same results as canonical route

---

#### Test 4.3: Incorrect Store Path

**Pattern**: `/api/v1/stores/ce-saladas/combo/` (singular, missing 's')

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combo/" \
  -H "Content-Type: application/json"
```

**Pass Criteria**:
- [ ] HTTP Status: 404 (route not found)

---

### TEST SUITE 5: CONTENT TYPE & HEADERS

#### Test 5.1: JSON Response Format

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/`

**Command**:
```bash
curl -X GET "http://localhost:8001/api/v1/stores/ce-saladas/combos/" \
  -H "Content-Type: application/json" \
  -v 2>&1 | grep -i "content-type"
```

**Pass Criteria**:
- [ ] Response `Content-Type: application/json`
- [ ] Response is valid JSON (parseable)

---

#### Test 5.2: POST Content-Type Validation

**Endpoint**: `POST /api/v1/stores/ce-saladas/cart/add-combo/`

**Command**:
```bash
curl -X POST "http://localhost:8001/api/v1/stores/ce-saladas/cart/add-combo/" \
  -H "Content-Type: text/plain" \
  -d 'not json' \
  -v 2>&1 | grep "HTTP"
```

**Pass Criteria**:
- [ ] Server accepts application/json
- [ ] Handles malformed data gracefully

---

#### Test 5.3: CORS Headers Present

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/`

**Command**:
```bash
curl -X OPTIONS "http://localhost:8001/api/v1/stores/ce-saladas/combos/" \
  -H "Origin: https://cesaladas.com.br" \
  -v 2>&1 | grep -i "access-control"
```

**Pass Criteria**:
- [ ] Response includes `Access-Control-Allow-Origin` header
- [ ] CORS properly configured

---

## Performance Tests

### PERF Test 1: List Endpoint Response Time

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/`

**Command**:
```bash
time curl -s "http://localhost:8001/api/v1/stores/ce-saladas/combos/" > /dev/null
```

**Expected**: < 200ms response time

**Pass Criteria**:
- [ ] Response time ≤ 200ms
- [ ] Consistent across multiple requests

---

### PERF Test 2: Detail Endpoint Response Time

**Endpoint**: `GET /api/v1/stores/ce-saladas/combos/{combo_id}/`

**Command**:
```bash
COMBO_ID="<from_test_1.1>"
time curl -s "http://localhost:8001/api/v1/stores/ce-saladas/combos/${COMBO_ID}/" > /dev/null
```

**Expected**: < 150ms response time

**Pass Criteria**:
- [ ] Response time ≤ 150ms

---

## Test Execution Summary

### Quick Test Script

```bash
#!/bin/bash

STORE_SLUG="ce-saladas"
BASE_URL="http://localhost:8001/api/v1/stores"

echo "Running Combo API Tests..."

# Test 1: List Combos
echo "Test 1: GET ${BASE_URL}/${STORE_SLUG}/combos/"
curl -s "${BASE_URL}/${STORE_SLUG}/combos/" | jq -r '.count' && echo "PASS" || echo "FAIL"

# Test 2: Filter by is_active
echo "Test 2: GET ${BASE_URL}/${STORE_SLUG}/combos/?is_active=true"
curl -s "${BASE_URL}/${STORE_SLUG}/combos/?is_active=true" | jq -r '.results | length' && echo "PASS" || echo "FAIL"

# Test 3: Invalid Store
echo "Test 3: GET ${BASE_URL}/invalid/combos/"
curl -s "${BASE_URL}/invalid/combos/" | jq -r '.detail' && echo "PASS (404)" || echo "FAIL"

# Test 4: Get Combo Detail
COMBO_ID=$(curl -s "${BASE_URL}/${STORE_SLUG}/combos/" | jq -r '.results[0].id // empty')
if [ -n "$COMBO_ID" ]; then
  echo "Test 4: GET ${BASE_URL}/${STORE_SLUG}/combos/${COMBO_ID}/"
  curl -s "${BASE_URL}/${STORE_SLUG}/combos/${COMBO_ID}/" | jq -r '.name' && echo "PASS" || echo "FAIL"
else
  echo "Test 4: SKIP (no combos found)"
fi

echo "Tests completed!"
```

---

## Test Coverage Matrix

| Feature | Test Case | Status |
|---------|-----------|--------|
| **List Combos** | No filters | [ ] |
| | Filter active | [ ] |
| | Filter inactive | [ ] |
| | Pagination | [ ] |
| | Max page size limit | [ ] |
| | Invalid store | [ ] |
| **Get Details** | Valid combo | [ ] |
| | Invalid UUID | [ ] |
| | Non-existent combo | [ ] |
| | Non-existent store | [ ] |
| | Tenant isolation | [ ] |
| **Add to Cart** | Guest user | [ ] |
| | Multiple quantity | [ ] |
| | Missing combo_id | [ ] |
| | Invalid combo_id | [ ] |
| | Invalid quantity | [ ] |
| | Non-existent combo | [ ] |
| | Missing selection | [ ] |
| | Too many selections | [ ] |
| | Sequential adds | [ ] |
| **URLs** | Canonical pattern | [ ] |
| | Legacy pattern | [ ] |
| | Incorrect path | [ ] |
| **Content Type** | JSON response | [ ] |
| | POST content-type | [ ] |
| | CORS headers | [ ] |
| **Performance** | List latency | [ ] |
| | Detail latency | [ ] |

---

## Notes

- Tests assume Docker containers are healthy
- Adjust timings if running on slower machines
- Some tests require sample data (combos with groups/variants)
- Update `store_slug` values based on your test database
- All timestamps are in ISO 8601 format with timezone

