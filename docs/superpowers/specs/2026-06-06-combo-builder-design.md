# Combo Builder System Design

**Date:** 2026-06-06  
**Author:** Claude Code  
**Status:** Design Phase  
**Target:** Pastita (server2 backend + pastita-dash frontend)

---

## 1. Executive Summary

Build a complete combo builder system that allows store admins to create product bundles with flexible selection rules, and customers to choose variants at purchase time. Each combo can have multiple product groups (e.g., Rondelli + Molho) with independent selection constraints and stock limits.

**Example:** "Compre 3 Leve 4" = 4 Rondelli sabores (obrigatório) + até 4 Molhos (opcional)

---

## 2. Requirements

### 2.1 Admin Requirements
- **Create combos** via pastita-dash (not Django admin)
- **Configure product groups** (product, required/optional, min/max selections, allow duplicates)
- **Set variant limits** (e.g., max 2 Frango per combo, respecting real stock)
- **See combo list** with status, pricing, active groups
- **Edit/duplicate/activate/deactivate** existing combos

### 2.2 Customer Requirements
- **View combo** in product detail modal
- **See available variants** with stock availability per variant
- **Select variants** respecting:
  - Group-level rules (min/max selections)
  - Variant-level limits (max per variant)
  - Real-time stock availability
- **Validate selections** before adding to cart
- **Add to cart** with selected variants saved

### 2.3 System Requirements
- **Stock validation:** Never exceed max_selections for a variant or group
- **Data persistence:** Save customer's selections in order
- **API consistency:** All combos use same validation rules
- **Backward compatibility:** Existing products/orders unaffected

---

## 3. Data Model

### 3.1 New Models

#### `ComboProductGroup`
Represents a product group within a combo with selection rules.

```python
class ComboProductGroup(models.Model):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    combo = ForeignKey(StoreCombo, on_delete=CASCADE, related_name='groups')
    product = ForeignKey(StoreProduct, on_delete=CASCADE)
    
    # Selection rules
    is_required = BooleanField(default=True)
    min_selections = PositiveIntegerField(default=1)
    max_selections = PositiveIntegerField(default=1)
    allow_duplicate_variants = BooleanField(default=False)
    
    # Metadata
    position = PositiveIntegerField(default=0)  # For ordering
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['combo', 'product']
        ordering = ['position']
```

#### `ComboProductGroupVariantLimit`
Defines stock limits per variant within a group.

```python
class ComboProductGroupVariantLimit(models.Model):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    group = ForeignKey(ComboProductGroup, on_delete=CASCADE, related_name='variant_limits')
    variant = ForeignKey(StoreProductVariant, on_delete=CASCADE)
    
    # Limit for this variant in this combo group
    max_selections = PositiveIntegerField(default=1)
    
    # Optional: price override (if variant costs different in combo)
    price_override = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['group', 'variant']
```

### 3.2 Modified Models

#### `StoreCombo` (existing)
No changes required. Already has: name, slug, price, description, image, is_active, featured, etc.

#### `StoreOrderComboItem` (existing, already created)
Already tracks customer selections:
- `selected_variant_ids` (list of variant UUIDs)
- `selected_variants_data` (denormalized data for display)

---

## 4. API Endpoints

### 4.1 GET `/api/v1/stores/{store_slug}/combos/{combo_id}/`

**Purpose:** Fetch combo details with all groups, variants, and stock info for customer modal.

**Response:**
```json
{
  "id": "combo-uuid",
  "name": "Compre 3 Leve 4",
  "slug": "compre-3-leve-4",
  "price": "45.00",
  "description": "4 Rondelli a preço especial",
  "image_url": "https://...",
  "is_active": true,
  "groups": [
    {
      "id": "group-1-uuid",
      "product_id": "rondelli-uuid",
      "product_name": "Rondelli",
      "is_required": true,
      "min_selections": 4,
      "max_selections": 4,
      "allow_duplicate_variants": true,
      "position": 1,
      "variants": [
        {
          "id": "variant-frango-uuid",
          "name": "Frango",
          "sku": "rondelli-frango",
          "stock": 5,
          "max_in_combo": 2
        },
        {
          "id": "variant-tomate-uuid",
          "name": "Tomate Seco",
          "sku": "rondelli-tomate",
          "stock": 3,
          "max_in_combo": 2
        }
      ]
    },
    {
      "id": "group-2-uuid",
      "product_id": "molho-uuid",
      "product_name": "Molho",
      "is_required": false,
      "min_selections": 0,
      "max_selections": 4,
      "allow_duplicate_variants": true,
      "position": 2,
      "variants": [
        {
          "id": "variant-branco-uuid",
          "name": "Molho Branco",
          "stock": 10,
          "max_in_combo": 2
        }
      ]
    }
  ]
}
```

### 4.2 POST `/api/v1/stores/{store_slug}/cart/add-combo/`

**Purpose:** Add combo to cart with customer's variant selections.

**Request:**
```json
{
  "combo_id": "combo-uuid",
  "quantity": 1,
  "selections": {
    "group-1-uuid": [
      "variant-frango-uuid",
      "variant-frango-uuid",
      "variant-tomate-uuid",
      "variant-queijo-uuid"
    ],
    "group-2-uuid": [
      "variant-branco-uuid",
      "variant-branco-uuid"
    ]
  }
}
```

**Response:** Same as POST /cart/add/ with combo item added

**Validation:**
- ✓ Group-level: min/max selections respected
- ✓ Variant-level: max_selections per variant not exceeded
- ✓ Required groups: must have selections
- ✓ Stock: real-time check against StoreProductVariant.stock
- ✓ Duplicates: allowed only if allow_duplicate_variants=true

**Error Examples:**
```json
{
  "error": "Validation failed",
  "details": {
    "group-1-uuid": "Must select exactly 4 variants, got 3"
  }
}
```

### 4.3 GET `/api/v1/stores/{store_slug}/combos/`

**Purpose:** List all combos for pastita-dash.

**Response:** Array of combos with summary info (name, price, # groups, is_active)

---

## 5. Frontend: pastita-dash Admin UI

### 5.1 Combo List Page (`/dashboard/combos`)

**Components:**
- Table with columns: Name, Price, Groups, Status, Actions
- Buttons: "New Combo", filters by status
- Row actions: Edit, Duplicate, Toggle Active, Delete

### 5.2 Combo Create/Edit Form (`/dashboard/combos/new` or `/dashboard/combos/{id}/edit`)

**Layout:**

**Section 1: Basic Info**
- Text input: Name
- Text input: Slug (auto-generated from name)
- Decimal input: Price
- Textarea: Description
- Image upload: Image
- Toggle: Is Active
- Toggle: Featured (optional)

**Section 2: Product Groups**
- "Add Group" button
- For each group (accordion/card):
  - Product selector (dropdown of StoreProducts)
  - Checkbox: "Required" (default: true)
  - Number input: Min Selections (default: 1)
  - Number input: Max Selections (default: 1)
  - Checkbox: "Allow Duplicate Variants" (default: false)
  - **Variants Table:**
    - Columns: Name, SKU, Stock, Max in Combo
    - Rows: All variants of selected product
    - Editable: "Max in Combo" field (number input)
    - Auto-populate Stock from StoreProductVariant.stock

**Buttons:**
- "Save & Preview" (shows modal preview of customer view)
- "Save"
- "Cancel"

### 5.3 Customer Modal (Product Detail)

**When product_type = 'combo':**

**Header:**
- Combo name, image, price, description

**Sections (one per group):**
- Group title (e.g., "Rondelli - Escolha exatamente 4 sabores")
- If required: "(Obrigatório)"
- If optional: "(Opcional)"
- Checkboxes for each variant:
  - Label: "Variant Name (X de Y disponíveis)"
  - Disabled if stock = 0 or max_in_combo already reached
  - Show real-time count: "Selected: X of max_selections"

**Validation Display:**
- Red border/alert if required group incomplete
- Green checkmark when all required groups complete

**Button:**
- "Adicionar ao Carrinho" (disabled until all required groups valid)

---

## 6. Backend Validation Logic

### 6.1 Selection Validator Class

```python
class ComboSelectionValidator:
    """Validates customer's combo selections against combo rules."""
    
    def validate(self, combo, selections):
        """
        selections: {group_id: [variant_id, variant_id, ...]}
        Returns: (is_valid, errors)
        """
        errors = {}
        
        for group in combo.groups.all():
            group_selections = selections.get(str(group.id), [])
            
            # Check required
            if group.is_required and not group_selections:
                errors[str(group.id)] = f"This group is required"
                continue
            
            # Check min/max
            count = len(group_selections)
            if count < group.min_selections:
                errors[str(group.id)] = f"Need at least {group.min_selections} items"
            if count > group.max_selections:
                errors[str(group.id)] = f"Maximum {group.max_selections} items allowed"
            
            # Check duplicates
            if not group.allow_duplicate_variants:
                unique = set(group_selections)
                if len(unique) < len(group_selections):
                    errors[str(group.id)] = "Cannot select same variant twice"
            
            # Check variant limits
            self._validate_variant_limits(group, group_selections, errors)
            
            # Check stock
            self._validate_stock(group, group_selections, errors)
        
        return len(errors) == 0, errors
    
    def _validate_variant_limits(self, group, selections, errors):
        """Check max_selections per variant."""
        from collections import Counter
        counts = Counter(selections)
        for variant_id, count in counts.items():
            limit = group.variant_limits.filter(variant_id=variant_id).first()
            if limit and count > limit.max_selections:
                errors[str(group.id)] = f"Max {limit.max_selections} of this variant"
    
    def _validate_stock(self, group, selections, errors):
        """Check real stock against selections."""
        from collections import Counter
        counts = Counter(selections)
        for variant_id, count in counts.items():
            variant = StoreProductVariant.objects.get(id=variant_id)
            if count > variant.stock:
                errors[str(group.id)] = f"Only {variant.stock} in stock"
```

### 6.2 Order Checkout Validation

Before creating order, validate combo selections in checkout endpoint:
- Call `ComboSelectionValidator.validate()`
- If invalid, return 400 with error details
- If valid, proceed to create order + `StoreOrderComboItem`

---

## 7. Data Flow Diagrams

### 7.1 Admin Creates Combo

```
Admin fills form in pastita-dash
├─ Basic info (name, price, image)
└─ Adds Groups
   ├─ Select Rondelli (required, min=4, max=4, allow_dup=true)
   │  └─ Configure variant limits (Frango: max=2, Tomate: max=2)
   └─ Select Molho (optional, min=0, max=4, allow_dup=true)
      └─ Configure variant limits

POST /api/v1/stores/{slug}/combos/ (create)
├─ Create StoreCombo
├─ Create 2 ComboProductGroups
└─ Create N ComboProductGroupVariantLimits

pastita-dash shows "Combo saved!"
```

### 7.2 Customer Buys Combo

```
Customer browses store, clicks combo product
│
GET /api/v1/stores/{slug}/combos/{id}/
│
Modal opens with all groups + variants + stock

Customer selects:
├─ 2x Frango + 1x Tomate + 1x Queijo (4 total) ✓
└─ 2x Molho Branco (2 total) ✓

POST /api/v1/stores/{slug}/cart/add-combo/
├─ Server validates selections (ComboSelectionValidator)
├─ Server creates StoreOrderComboItem with selections
└─ Returns 200 with cart updated

Frontend adds item to cart, closes modal
```

---

## 8. Migration Strategy

### Phase 1: Database
1. Create migration for `ComboProductGroup` model
2. Create migration for `ComboProductGroupVariantLimit` model
3. Run migrations: `python manage.py migrate`

### Phase 2: Backend API
1. Create `ComboProductGroupSerializer` and `ComboProductGroupVariantLimitSerializer`
2. Create `ComboSelectionValidator` class
3. Add/update endpoints: GET combo, POST add-combo
4. Add validation in checkout

### Phase 3: Frontend (pastita-dash)
1. Create ComboList page
2. Create ComboForm component (with group management)
3. Update ProductDetail modal to detect combo type
4. Add combo picker UI to modal

### Phase 4: Testing & QA
1. Unit tests: validators, serializers
2. Integration tests: API endpoints
3. UI tests: pastita-dash forms, modal
4. Manual testing: end-to-end flow

---

## 9. Edge Cases & Constraints

| Case | Handling |
|------|----------|
| Combo with 0 groups | UI prevents save |
| No variants for product | API returns empty variants list; modal shows "No options" |
| Stock changes after customer selects | Re-validate at checkout; reject if stock insufficient |
| Variant deleted | ComboProductGroupVariantLimit cascades delete |
| Allow_duplicates=false, selected same variant twice | Validator rejects with error message |
| Customer tries to exceed max_selections | Frontend UI disables; backend rejects |
| Required group not filled | "Adicionar ao Carrinho" button disabled; checkout validation fails |

---

## 10. Success Criteria

- ✅ Admin can create combos with multiple groups in pastita-dash (no Django admin)
- ✅ Each group has independent selection rules (required, min/max, duplicates)
- ✅ Variant limits enforce stock constraints (max 2 Frango, etc.)
- ✅ Customer modal validates in real-time (disabled buttons, error messages)
- ✅ API validates all rules before accepting combo in cart
- ✅ Order detail shows customer's selected variants
- ✅ No data loss: selections saved in StoreOrderComboItem

---

## 11. Out of Scope

- Analytics on combo purchases (separate feature)
- A/B testing combo pricing
- Combo recommendations engine
- Bulk import/export of combos

---

## 12. Open Questions / Notes

- **Price overrides per variant:** ComboProductGroupVariantLimit has optional `price_override`, but "Combo" always uses combo.price. Confirm if variants should have different prices in future.
- **Combo in combo:** Can you nest combos? Not supporting yet; simplify first.
- **Historical combo changes:** If admin edits combo after purchase, old order still shows original selections (good). Confirm we don't need audit trail.

---

## Appendix: Model Relationships

```
StoreCombo
├─ groups: ComboProductGroup[]
│  ├─ product: StoreProduct
│  └─ variant_limits: ComboProductGroupVariantLimit[]
│     └─ variant: StoreProductVariant

StoreOrderItem
└─ combo_selections: StoreOrderComboItem[]
   ├─ combo: StoreCombo
   └─ selected_variant_ids: [uuid]
```
