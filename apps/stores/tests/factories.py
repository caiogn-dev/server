"""
Test factories for stores app.
Provides minimal helpers using real models — do NOT invent fields.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreProduct, StoreProductVariant, StoreCombo
from apps.stores.models.combo_group import (
    ComboProductGroup,
    ComboProductGroupVariantLimit,
    ComboProductGroupProductOption,
)

User = get_user_model()

_counter = [0]


def _uid():
    _counter[0] += 1
    return _counter[0]


def make_store(name=None, slug=None):
    """Create a minimal Store with a unique slug."""
    n = _uid()
    name = name or f"Test Store {n}"
    slug = slug or f"test-store-{n}"
    owner = User.objects.create_user(username=f"owner-{n}", password="pw")
    return Store.objects.create(name=name, slug=slug, owner=owner, status="active")


def make_product(store, name=None, slug=None, price=Decimal("10.00")):
    """Create a minimal StoreProduct."""
    n = _uid()
    name = name or f"Product {n}"
    slug = slug or f"product-{n}"
    return StoreProduct.objects.create(
        store=store,
        name=name,
        slug=slug,
        price=price,
        track_stock=False,
        stock_quantity=0,
    )


def make_variant(product, name=None, price=None):
    """Create a minimal StoreProductVariant."""
    n = _uid()
    name = name or f"Variant {n}"
    return StoreProductVariant.objects.create(
        product=product,
        name=name,
        price=price,
        stock_quantity=10,
    )


def make_combo_with_groups(groups=3, variants=2, options=2, store=None):
    """
    Create a StoreCombo with `groups` ComboProductGroups,
    each having `variants` variant_limits and `options` product_options.

    If `store` is None, a fresh Store is created; pass an existing `store` to
    create multiple combos in the same tenant (necessário para provar O(1) em
    relação ao número de grupos serializando combos de tamanhos diferentes).

    Returns (store, combo).
    """
    if store is None:
        store = make_store()

    n = _uid()
    combo = StoreCombo.objects.create(
        store=store,
        name=f"Test Combo {n}",
        slug=f"test-combo-{n}",
        price=Decimal("50.00"),
        is_active=True,
    )

    for g_idx in range(groups):
        # Anchor product for this group
        anchor = make_product(store, name=f"Anchor {g_idx}", slug=f"anchor-{_uid()}")

        group = ComboProductGroup.objects.create(
            combo=combo,
            product=anchor,
            is_required=True,
            min_selections=1,
            max_selections=variants,
            position=g_idx,
        )

        # Variant limits
        for v_idx in range(variants):
            variant_product = make_product(
                store,
                name=f"VProd g{g_idx} v{v_idx}",
                slug=f"vprod-{_uid()}",
            )
            variant = make_variant(variant_product, name=f"Var g{g_idx} v{v_idx}")
            ComboProductGroupVariantLimit.objects.create(
                group=group,
                variant=variant,
                max_selections=1,
            )

        # Product options (skip unique_together conflict by using distinct products)
        for o_idx in range(options):
            opt_product = make_product(
                store,
                name=f"OptProd g{g_idx} o{o_idx}",
                slug=f"optprod-{_uid()}",
            )
            ComboProductGroupProductOption.objects.create(
                group=group,
                product=opt_product,
                max_selections=1,
                position=o_idx,
            )

    return store, combo
