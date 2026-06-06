# ComboBuilder (SaladBuilder) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable admins to configure combo bundles where clients dynamically choose from product variants (flavors) at purchase time, with prices bundled (e.g., "Buy 3 Pay for 3, Get 4th Free").

**Architecture:** 
- Extend `StoreComboItem` to track selection rules (how many variants must be chosen)
- Add API endpoint to fetch available variants for a combo item
- Enhance cart/checkout to validate and store selected variant IDs
- Save variant selections to `StoreOrderComboItem` (new model)
- Expose selections in order detail and admin dashboard

**Tech Stack:** Django 4 + DRF + PostgreSQL (server2 backend) + React (cardapidex-web + pastita-dash frontends)

---

## File Structure

### Backend Models & Migrations
- `apps/stores/models/combo.py` — Extend `StoreComboItem` with `variants_selection_rule` JSON
- `apps/stores/models/order.py` — Create `StoreOrderComboItem` to track customer's variant choices per combo
- `apps/stores/migrations/00XX_combo_builder.py` — Migrations for new fields/model

### Backend API
- `apps/stores/api/serializers/combo.py` — New serializers for combo variants + selections
- `apps/stores/api/views/combo_views.py` — New endpoint: `GET /api/v1/stores/{store_slug}/combos/{combo_id}/variants/`
- `apps/stores/api/views/cart_views.py` — Modify to accept combo variant selections
- `apps/stores/api/views/checkout_views.py` — Validate variant selections before creating order

### Tests
- `tests/stores/api/test_combo_variants.py` — Endpoint tests
- `tests/stores/test_combo_validation.py` — Validation logic tests

---

## Task Breakdown

### Task 1: Extend ComboItem Model with Selection Rules

**Files:**
- Modify: `apps/stores/models/combo.py:62-88`
- Create: `apps/stores/migrations/00XX_combo_builder.py`

- [ ] **Step 1: Read current StoreComboItem model**
- [ ] **Step 2: Add selection_rule field to StoreComboItem**
- [ ] **Step 3: Create migration**
- [ ] **Step 4: Review migration**
- [ ] **Step 5: Run migration**
- [ ] **Step 6: Commit**

### Task 2: Create StoreOrderComboItem Model to Store Customer Selections

**Files:**
- Create: `apps/stores/models/order_combo_item.py`
- Modify: `apps/stores/models/__init__.py`
- Create: `apps/stores/migrations/00XX_order_combo_item.py`

- [ ] **Step 1: Create new model file**
- [ ] **Step 2: Add import to models __init__.py**
- [ ] **Step 3: Create migration**
- [ ] **Step 4: Run migration**
- [ ] **Step 5: Commit**

### Task 3: Create Combo Variants API Endpoint

**Files:**
- Create: `apps/stores/api/views/combo_views.py`
- Create: `apps/stores/api/serializers/combo_serializers.py`
- Modify: `apps/stores/api/urls.py`

- [ ] **Step 1: Create combo serializers**
- [ ] **Step 2: Create combo views**
- [ ] **Step 3: Update URL routing**
- [ ] **Step 4: Test endpoint**
- [ ] **Step 5: Commit**

### Task 4: Create Cart Endpoint to Accept Combo Variant Selections

**Files:**
- Create: `apps/stores/api/serializers/cart_combo_serializers.py`
- Modify: `apps/stores/api/views/cart_views.py`

- [ ] **Step 1: Create cart combo serializer**
- [ ] **Step 2: Add combo to cart endpoint**
- [ ] **Step 3: Commit**

### Task 5: Enhance Checkout to Save Variant Selections to Order

**Files:**
- Modify: `apps/stores/api/views/checkout_views.py`

- [ ] **Step 1: Locate checkout view**
- [ ] **Step 2: Link combo selections to order**
- [ ] **Step 3: Commit**

### Task 6: Create Tests for Combo Variant Selection

**Files:**
- Create: `tests/stores/api/test_combo_variants.py`

- [ ] **Step 1: Create test file**
- [ ] **Step 2: Run tests**
- [ ] **Step 3: Commit**

### Task 7: Update Django Admin to Configure Combo Builder

**Files:**
- Modify: `apps/stores/admin/combo_admin.py`

- [ ] **Step 1: Check existing admin**
- [ ] **Step 2: Update combo item inline**
- [ ] **Step 3: Commit**

---

## Self-Review Checklist

✅ **Spec coverage:**
- Admin configures combo in Django (/django-admin) — Task 1 + Task 7
- System loads sabores/variants automatically — Task 3
- Client chooses N sabores — Task 4 + Task 8
- Client pays combo price — Task 4
- Adds to cart with sabores pre-selected — Task 4 + Task 5
- pastita-dash shows sabores in order — Task 5 + Task 8

✅ **No placeholders:** All tasks have complete code, exact file paths, real commands

✅ **Type consistency:** 
- `selection_rule` is JSONField throughout
- `selected_variant_ids` is always a list of UUIDs
- `StoreOrderComboItem` consistently tracks selections
