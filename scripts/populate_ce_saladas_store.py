#!/usr/bin/env python
"""
Populate or update CE Saladas store for local development.

Usage:
    python manage.py shell -c "exec(open('scripts/populate_ce_saladas_store.py').read())"
"""

import copy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.stores.models import (
    Store,
    StoreCategory,
    StoreDeliveryZone,
    StoreProduct,
    StoreProductType,
)


User = get_user_model()

REFERENCE_STORE_SLUG = "pastita"
TARGET_STORE_SLUG = "ce-saladas"

DEFAULT_COORDS = {
    "latitude": Decimal("-10.1852600"),
    "longitude": Decimal("-48.3034780"),
}

DEFAULT_OPERATING_HOURS = {
    "monday": {"open": "11:00", "close": "22:00"},
    "tuesday": {"open": "11:00", "close": "22:00"},
    "wednesday": {"open": "11:00", "close": "22:00"},
    "thursday": {"open": "11:00", "close": "22:00"},
    "friday": {"open": "11:00", "close": "23:00"},
    "saturday": {"open": "11:00", "close": "23:00"},
    "sunday": {"open": "11:00", "close": "21:00"},
}


def resolve_owner(reference_store):
    if reference_store and reference_store.owner_id:
        return reference_store.owner

    owner = User.objects.filter(is_superuser=True).order_by("id").first()
    if owner:
        return owner

    owner = User.objects.filter(is_staff=True).order_by("id").first()
    if owner:
        return owner

    owner = User.objects.order_by("id").first()
    if owner:
        return owner

    raise RuntimeError("No users found. Create a user before running this script.")


def build_store_defaults(reference_store, owner):
    defaults = {
        "name": "Ce Saladas",
        "description": "Loja Ce Saladas para ambiente local de desenvolvimento.",
        "store_type": Store.StoreType.FOOD,
        "status": Store.StoreStatus.ACTIVE,
        "email": "contato@cesaladas.com.br",
        "phone": "",
        "whatsapp_number": "",
        "address": "",
        "city": "",
        "state": "",
        "zip_code": "",
        "country": "BR",
        "latitude": DEFAULT_COORDS["latitude"],
        "longitude": DEFAULT_COORDS["longitude"],
        "primary_color": "#2E7D32",
        "secondary_color": "#F9A825",
        "currency": "BRL",
        "timezone": "America/Sao_Paulo",
        "tax_rate": Decimal("0.00"),
        "delivery_enabled": True,
        "pickup_enabled": True,
        "min_order_value": Decimal("0.00"),
        "free_delivery_threshold": Decimal("100.00"),
        "default_delivery_fee": Decimal("9.00"),
        "operating_hours": copy.deepcopy(DEFAULT_OPERATING_HOURS),
        "owner": owner,
        "metadata": {
            "seed_source": "scripts/populate_ce_saladas_store.py",
            "location_source": REFERENCE_STORE_SLUG if reference_store else "default",
            # ── Cálculo dinâmico de frete ──────────────────────────────────
            # R$9,00 plano até 4 km → +R$1,00/km após isso → >16 km = a combinar
            "delivery_base_fee": "9.00",
            "delivery_fee_per_km": "1.00",
            "delivery_flat_km": "4.0",
            "delivery_max_km": "16.0",
            # ── Zonas fixas por bairro / região ───────────────────────────
            # Verificadas via reverse-geocode antes do cálculo por km.
            # surcharge_on_km=True → soma 'surcharge' à taxa por km (condos fechados).
            "fixed_price_zones": [
                # Regiões com taxa fixa
                {
                    "name": "Aurenys / Bertaville",
                    "fee": 40.00,
                    "keywords": ["Aurenys", "Bertaville"],
                },
                {
                    "name": "Taquaralto",
                    "fee": 40.00,
                    "keywords": ["Taquaralto"],
                },
                {
                    "name": "Aeroporto",
                    "fee": 45.00,
                    "keywords": ["Aeroporto", "Jardim Aeroporto", "Setor Aeroporto"],
                },
                {
                    "name": "Luzimangues",
                    "fee": 45.00,
                    "keywords": ["Luzimangues"],
                },
                {
                    "name": "Taquari",
                    "fee": 50.00,
                    "keywords": ["Taquari"],
                },
                # Condomínios com taxa fixa
                {
                    "name": "Caribe / Polinésia",
                    "fee": 25.00,
                    "keywords": ["Caribe", "Polinesia", "Polinésia"],
                },
                {
                    "name": "Mirante do Lago",
                    "fee": 25.00,
                    "keywords": ["Mirante do Lago", "Mirante Lago"],
                },
                # Condomínios fechados: taxa por km + R$5,00
                {
                    "name": "Alphaville / Privillege / Aldeia do Sol",
                    "surcharge_on_km": True,
                    "surcharge": 5.00,
                    "keywords": ["Alphaville", "Privillege", "Privilege", "Aldeia do Sol"],
                },
            ],
        },
    }

    if reference_store:
        defaults.update(
            {
                "address": reference_store.address,
                "city": reference_store.city,
                "state": reference_store.state,
                "zip_code": reference_store.zip_code,
                "country": reference_store.country or "BR",
                "latitude": reference_store.latitude or DEFAULT_COORDS["latitude"],
                "longitude": reference_store.longitude or DEFAULT_COORDS["longitude"],
                "delivery_enabled": reference_store.delivery_enabled,
                "pickup_enabled": reference_store.pickup_enabled,
                "min_order_value": reference_store.min_order_value,
                "free_delivery_threshold": reference_store.free_delivery_threshold,
                "default_delivery_fee": reference_store.default_delivery_fee,
                "operating_hours": copy.deepcopy(
                    reference_store.operating_hours or DEFAULT_OPERATING_HOURS
                ),
            }
        )

        if reference_store.phone and not defaults["phone"]:
            defaults["phone"] = reference_store.phone
        if reference_store.whatsapp_number:
            defaults["whatsapp_number"] = reference_store.whatsapp_number

    return defaults


def sync_categories(reference_store, target_store):
    if not reference_store:
        return 0

    created_or_updated = 0
    parent_map = {}

    source_categories = list(
        reference_store.categories.all().order_by("sort_order", "name")
    )
    for source in source_categories:
        category, _ = StoreCategory.objects.update_or_create(
            store=target_store,
            slug=source.slug,
            defaults={
                "name": source.name,
                "description": source.description,
                "image_url": source.image_url,
                "sort_order": source.sort_order,
                "is_active": source.is_active,
                "parent": None,
            },
        )
        parent_map[source.id] = category
        created_or_updated += 1

    for source in source_categories:
        if source.parent_id:
            category = parent_map[source.id]
            parent = parent_map.get(source.parent_id)
            if parent and category.parent_id != parent.id:
                category.parent = parent
                category.save(update_fields=["parent", "updated_at"])

    return created_or_updated


def sync_product_types(reference_store, target_store):
    if not reference_store:
        return {}, 0

    created_or_updated = 0
    type_map = {}
    source_types = list(reference_store.product_types.all().order_by("sort_order", "name"))
    for source in source_types:
        product_type, _ = StoreProductType.objects.update_or_create(
            store=target_store,
            slug=source.slug,
            defaults={
                "name": source.name,
                "description": source.description,
                "icon": source.icon,
                "custom_fields": copy.deepcopy(source.custom_fields or []),
                "sort_order": source.sort_order,
                "is_active": source.is_active,
                "show_in_menu": source.show_in_menu,
            },
        )
        type_map[source.id] = product_type
        created_or_updated += 1

    return type_map, created_or_updated


def sync_products(reference_store, target_store, type_map):
    if not reference_store:
        return 0

    category_map = {
        c.slug: c for c in target_store.categories.all()
    }

    created_or_updated = 0
    source_products = list(reference_store.products.all().order_by("sort_order", "name"))
    for source in source_products:
        category = category_map.get(source.category.slug) if source.category_id else None
        product_type = type_map.get(source.product_type_id)

        _, _created = StoreProduct.objects.update_or_create(
            store=target_store,
            slug=source.slug,
            defaults={
                "category": category,
                "product_type": product_type,
                "type_attributes": copy.deepcopy(source.type_attributes or {}),
                "name": source.name,
                "description": source.description,
                "short_description": source.short_description,
                "sku": source.sku,
                "barcode": source.barcode,
                "price": source.price,
                "compare_at_price": source.compare_at_price,
                "cost_price": source.cost_price,
                "track_stock": source.track_stock,
                "stock_quantity": source.stock_quantity,
                "low_stock_threshold": source.low_stock_threshold,
                "allow_backorder": source.allow_backorder,
                "status": source.status,
                "featured": source.featured,
                "main_image_url": source.main_image_url,
                "images": copy.deepcopy(source.images or []),
                "meta_title": source.meta_title,
                "meta_description": source.meta_description,
                "weight": source.weight,
                "weight_unit": source.weight_unit,
                "dimensions": copy.deepcopy(source.dimensions or {}),
                "attributes": copy.deepcopy(source.attributes or {}),
                "tags": copy.deepcopy(source.tags or []),
                "sort_order": source.sort_order,
                "view_count": 0,
                "sold_count": 0,
            },
        )
        created_or_updated += 1

    return created_or_updated


def sync_delivery_zones(reference_store, target_store):
    if not reference_store:
        return 0

    created_or_updated = 0
    source_zones = list(
        reference_store.delivery_zones.all().order_by("sort_order", "name")
    )
    for source in source_zones:
        _, _ = StoreDeliveryZone.objects.update_or_create(
            store=target_store,
            name=source.name,
            zone_type=source.zone_type,
            distance_band=source.distance_band,
            defaults={
                "min_km": source.min_km,
                "max_km": source.max_km,
                "zip_code_start": source.zip_code_start,
                "zip_code_end": source.zip_code_end,
                "min_minutes": source.min_minutes,
                "max_minutes": source.max_minutes,
                "polygon_coordinates": copy.deepcopy(source.polygon_coordinates or []),
                "delivery_fee": source.delivery_fee,
                "min_fee": source.min_fee,
                "fee_per_km": source.fee_per_km,
                "estimated_minutes": source.estimated_minutes,
                "estimated_days": source.estimated_days,
                "color": source.color,
                "is_active": source.is_active,
                "sort_order": source.sort_order,
            },
        )
        created_or_updated += 1

    return created_or_updated


@transaction.atomic
def run():
    reference_store = Store.objects.filter(slug=REFERENCE_STORE_SLUG).first()
    owner = resolve_owner(reference_store)
    defaults = build_store_defaults(reference_store, owner)

    store, created = Store.objects.update_or_create(
        slug=TARGET_STORE_SLUG,
        defaults=defaults,
    )
    store.staff.add(owner)

    categories_count = sync_categories(reference_store, store)
    type_map, product_types_count = sync_product_types(reference_store, store)
    products_count = sync_products(reference_store, store, type_map)
    zones_count = sync_delivery_zones(reference_store, store)

    status = "created" if created else "updated"
    print(f"Store {status}: {store.name} ({store.slug})")
    print(f"Location: lat={store.latitude} lng={store.longitude}")
    print(f"Address: {store.address}, {store.city}/{store.state}")
    print(f"Categories synced: {categories_count}")
    print(f"Product types synced: {product_types_count}")
    print(f"Products synced: {products_count}")
    print(f"Delivery zones synced: {zones_count}")
    print("Done.")


run()
