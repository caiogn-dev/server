# Store Population Guide

This document explains how to populate stores in Pastita with menus, categories, products, delivery zones, and WhatsApp integration.

## Overview

The population system provides idempotent management commands to initialize three restaurants with real data:

1. **Cê Saladas** — salad restaurant in Palmas, Tocantins
2. **Pastita** — pasta/dough restaurant (Rondelli focus)
3. **Kero Kero** — fried snacks (salgadinhos) restaurant

Each command:
- Creates or updates the Store entity
- Configures WhatsApp Business Account (Cê Saladas only)
- Creates product categories
- Creates products with automatic image optimization (WebP)
- Creates 16 graduated delivery zones (0-17km distance bands)

## Quick Start

### Populate all three stores

```bash
python manage.py populate_all_stores --all
```

### Populate a specific store

```bash
python manage.py populate_ce_saladas_menu
python manage.py populate_pastita_menu
python manage.py populate_kero_kero_menu
```

### Force repopulation (overwrite existing data)

```bash
python manage.py populate_all_stores --all --force
```

### Populate multiple specific stores

```bash
python manage.py populate_all_stores --store=ce-saladas --store=pastita
```

## Architecture

### Shared Data

All three stores use the same:

**Location (Palmas, Tocantins):**
```python
SHARED_LOCATION = {
    "latitude": Decimal("-10.1852683"),
    "longitude": Decimal("-48.3036368"),
    "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins",
    "city": "Palmas",
    "state": "TO",
    "zip_code": "72000-000",
    "country": "BR",
}
```

**Operating Hours (Mon-Sat 8am-5pm, Sunday closed):**
```python
SHARED_OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "17:00"},
    "sunday": {"open": "00:00", "close": "00:00"},
}
```

**Delivery Zones (16 bands with graduated fees):**
- 0-2km: R$7.00
- 2-3km: R$8.00
- 3-5km: R$9.00
- ...
- 17km: R$28.00

All distances and fees are Decimal-based for financial accuracy.

### Store-Specific Data

**Cê Saladas:**
- Colors: Green #2E7D32, Yellow #F9A825
- WhatsApp: WABA 1537842617304215, Phone ID 941408229062882
- 1 Category: Saladas Especiais
- 7 Products: Various salads with premium proteins
- Auto-response + human handoff enabled

**Pastita:**
- Colors: Orange, Yellow
- No WhatsApp integration yet
- Product Types (Rondelli, Molho)
- 3 Categories: Rondelli, Molhos, Promoções
- 2 Products: Rondelli variations

**Kero Kero:**
- Colors: Pink #E91E63, Light Pink #FF6EC7
- 8 Categories: Mais Pedidos, Combos com Refri, Salgadinhos Fritos, Kit Festa, Congelados, Bolos e Doces, Lanches e Massas, Bebidas
- 3+ Products: Salgadinhos, Kits, and specials

## Image Optimization

All product images are automatically optimized during population:

1. **Conversion:** PNG/JPG → WebP format
2. **Resizing:** Maintains aspect ratio, max 600x600px
3. **Quality:** 80% quality for optimal balance
4. **Storage:** Optimized images saved in `media/stores/products/{store_slug}/`

Images that don't exist on disk are skipped with a warning (logged, not fatal).

### Image Paths

Place images in `media/stores/products/{store_slug}/`:

```
media/stores/products/ce-saladas/
├── tilapia.webp
├── especial-frango.png
├── basic-lombo.png
├── salmao.png
├── almondegas.png
├── queridinha.png
└── camarao.png

media/stores/products/pastita/
├── rondelli-tomate-seco.png
└── rondelli-frango-queijo.png

media/stores/products/kero-kero/
├── combo-25-fritos.png
├── fritos-sortidos-50.png
└── kit-festa.png
```

## Idempotency

All commands use `update_or_create()` for:
- Store
- WhatsApp Account (Cê Saladas)
- Categories
- Products
- Delivery Zones

This means:

1. **First run:** Creates all entities
2. **Subsequent runs:** Updates matching records (by slug/phone_number_id)
3. **With `--force`:** Explicit override intent (same as re-run)

```python
# Idempotent pattern used across all commands
Store.objects.update_or_create(
    slug=STORE_SLUG,
    defaults={...}
)
```

## Testing

All population commands have integration tests in `tests/stores/management/commands/test_populate_stores.py`:

```bash
# Test single store
python manage.py test tests.stores.management.commands.test_populate_stores.PopulateCeSaladasTestCase -v 2

# Test all population commands
python manage.py test tests.stores.management.commands.test_populate_stores -v 2
```

Tests verify:
- Store creation with correct colors/phone/hours
- WhatsApp account setup (Cê Saladas)
- Categories created
- Products created
- Delivery zones (exactly 16)
- Idempotency (multiple runs don't duplicate data)

## File Structure

```
apps/stores/
├── management/commands/
│   ├── populate_ce_saladas_menu.py          # Cê Saladas with WhatsApp
│   ├── populate_pastita_menu.py             # Pastita without WhatsApp
│   ├── populate_kero_kero_menu.py           # Kero Kero without WhatsApp
│   └── populate_all_stores.py               # Master orchestrator
├── utils/
│   ├── __init__.py
│   └── image_optimizer.py                   # ImageOptimizer class
└── models.py                                 # Store, StoreCategory, StoreProduct, StoreDeliveryZone

tests/stores/
├── utils/
│   └── test_image_optimizer.py              # ImageOptimizer tests
└── management/commands/
    └── test_populate_stores.py              # Integration tests
```

## ImageOptimizer Class

Located in `apps/stores/utils/image_optimizer.py`:

```python
from apps.stores.utils.image_optimizer import ImageOptimizer

optimizer = ImageOptimizer()

# Optimize a single image
optimized_path = optimizer.optimize('/path/to/image.png', max_width=600, max_height=600)
# Returns: '/path/to/image.webp' or None on failure
```

Handles:
- RGBA → RGB conversion (white background)
- Aspect ratio preservation
- Max dimension constraints
- WebP compression (quality=80)
- Error logging (returns None on failure, does not raise)

## Adding a New Store

1. Create `apps/stores/management/commands/populate_{store_slug}_menu.py`
2. Import shared location, hours, delivery zones
3. Define store-specific constants (CATEGORIES, PRODUCTS)
4. Implement Command class with @transaction.atomic
5. Follow the 5-phase pattern:
   - Phase 1: Store creation
   - Phase 2: WhatsApp (if needed)
   - Phase 3: Categories
   - Phase 4: Products with image optimization
   - Phase 5: Delivery zones
6. Add integration tests to `test_populate_stores.py`
7. Update `populate_all_stores.py` with new store mapping
8. Update this document with store details

## Troubleshooting

### Images not optimizing

**Symptom:** Products created but `main_image_url` is empty

**Cause:** Image files don't exist at expected path

**Fix:** Check `media/stores/products/{store_slug}/` and ensure PNG/JPG files exist. Logs show missing file warnings. Creating missing images and re-running with `--force` will add them.

### Delivery zones not created

**Symptom:** 0 delivery zones after population

**Cause:** Database constraint or transaction rollback

**Fix:** Check logs for SQL errors. Ensure all zone data is valid (Decimal, not float). Transaction.atomic means entire command rolls back on any error.

### WhatsApp account not linked

**Symptom:** Store.whatsapp_account is null after populate_ce_saladas_menu

**Cause:** WhatsApp account created but not assigned to store

**Fix:** The command includes `store.whatsapp_account = wa_account` and `store.save()` which should work. If it fails, check logs for FK constraint errors or missing WhatsAppAccount model.

### Idempotency not working

**Symptom:** Running populate twice creates duplicate products

**Cause:** Product slug mismatch

**Fix:** Products use `StoreProduct.objects.update_or_create(store=store, slug=slugify(name), ...)`. Ensure product names are identical on re-runs. Use `--force` to explicitly force overwrites.

## Production Considerations

**Backup before population:**

```bash
# Backup PostgreSQL
docker compose exec db pg_dump -U postgres pastita > backup_pre_population.sql

# Run population with --force
python manage.py populate_all_stores --all --force

# Verify data in admin or API
curl https://backend.pastita.com.br/api/v1/public/ce-saladas/products/
```

**Metrics to monitor:**

- Store created: `Store.objects.count()`
- Products per store: `StoreProduct.objects.filter(store__slug='ce-saladas').count()`
- Delivery zones per store: `StoreDeliveryZone.objects.filter(store__slug='ce-saladas').count()` (should be 16)
- Image optimization: Check `media/stores/products/` for `.webp` files

## References

- `apps.stores.models.Store` — Multi-tenant store root model
- `apps.stores.models.StoreCategory` — Product categories per store
- `apps.stores.models.StoreProduct` — Individual products with pricing
- `apps.stores.models.StoreDeliveryZone` — Distance-based delivery pricing
- `apps.whatsapp.models.WhatsAppAccount` — WhatsApp Business Account integration
- `apps.stores.utils.ImageOptimizer` — Image conversion and optimization utility
