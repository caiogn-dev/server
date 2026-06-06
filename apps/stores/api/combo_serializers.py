"""
Serializers for combo-related models: ComboProductGroup, ComboProductGroupVariantLimit, and StoreCombo detail.

These serializers support the Combo Builder system where admins can create product bundles with
flexible selection rules, and customers can choose variants at purchase time.

Reference: docs/superpowers/specs/2026-06-06-combo-builder-design.md
"""
from decimal import Decimal
from rest_framework import serializers
from apps.stores.models import (
    StoreCombo,
    StoreProduct,
    StoreProductVariant,
)
from apps.stores.models.combo_group import (
    ComboProductGroup,
    ComboProductGroupVariantLimit,
)


class ComboProductGroupVariantLimitSerializer(serializers.ModelSerializer):
    """
    Serializer for ComboProductGroupVariantLimit model.

    Represents stock/selection limits per variant within a combo group.
    Includes variant details for display in admin UI and customer modal.

    Fields:
        - id: UUID primary key
        - variant_id: FK to StoreProductVariant
        - variant_name: Read-only variant name
        - variant_sku: Read-only variant SKU
        - stock: Read-only current stock from StoreProductVariant
        - max_selections: Max times this variant can be selected in combo
        - price_override: Optional price override for this variant in combo
    """

    variant_id = serializers.PrimaryKeyRelatedField(
        source='variant.id',
        read_only=True
    )
    variant_name = serializers.CharField(source='variant.name', read_only=True)
    variant_sku = serializers.CharField(source='variant.sku', read_only=True, allow_blank=True)
    stock = serializers.IntegerField(source='variant.stock_quantity', read_only=True)

    class Meta:
        model = ComboProductGroupVariantLimit
        fields = [
            'id',
            'variant_id',
            'variant_name',
            'variant_sku',
            'stock',
            'max_selections',
            'price_override',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'variant_id',
            'variant_name',
            'variant_sku',
            'stock',
            'created_at',
            'updated_at',
        ]


class ComboProductGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for ComboProductGroup model.

    Represents a product group within a combo with selection rules.
    Includes nested variant_limits for full combo configuration.

    Fields:
        - id: UUID primary key
        - product_id: FK to StoreProduct
        - product_name: Read-only product name
        - is_required: Whether group must have selections
        - min_selections: Minimum variants to select from this group
        - max_selections: Maximum variants to select from this group
        - allow_duplicate_variants: Whether same variant can be selected multiple times
        - position: Display order within combo
        - variant_limits: Nested serializer for per-variant limits
    """

    product_id = serializers.PrimaryKeyRelatedField(
        source='product.id',
        read_only=True
    )
    product_name = serializers.CharField(source='product.name', read_only=True)
    variant_limits = ComboProductGroupVariantLimitSerializer(many=True, read_only=True)

    class Meta:
        model = ComboProductGroup
        fields = [
            'id',
            'product_id',
            'product_name',
            'is_required',
            'min_selections',
            'max_selections',
            'allow_duplicate_variants',
            'position',
            'variant_limits',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'product_id',
            'product_name',
            'variant_limits',
            'created_at',
            'updated_at',
        ]


class ComboDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for StoreCombo with nested groups and variants (detailed view).

    Used for customer modal display and admin detail view. Includes all groups
    with their variants and stock information.

    API Response Example:
    {
        "id": "combo-uuid",
        "name": "Compre 3 Leve 4",
        "slug": "compre-3-leve-4",
        "price": "45.00",
        "compare_at_price": "59.90",
        "description": "4 Rondelli a preço especial",
        "image": "https://...",
        "is_active": true,
        "featured": false,
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
                "variant_limits": [
                    {
                        "id": "limit-1-uuid",
                        "variant_id": "variant-frango-uuid",
                        "variant_name": "Frango",
                        "variant_sku": "rondelli-frango",
                        "stock": 5,
                        "max_selections": 2,
                        "price_override": null
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """

    groups = ComboProductGroupSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCombo
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'price',
            'compare_at_price',
            'image',
            'image_url',
            'is_active',
            'featured',
            'track_stock',
            'stock_quantity',
            'sort_order',
            'groups',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'image_url',
            'groups',
            'created_at',
            'updated_at',
        ]

    def get_image_url(self, obj):
        """Return absolute URL for combo image."""
        return obj.get_image_url()


class ComboListSerializer(serializers.ModelSerializer):
    """
    Serializer for StoreCombo list view (summary).

    Used for combo listing in admin dashboard. Includes group count and summary info.
    """

    groups_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCombo
        fields = [
            'id',
            'name',
            'slug',
            'price',
            'compare_at_price',
            'image_url',
            'is_active',
            'featured',
            'groups_count',
            'sort_order',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'image_url',
            'groups_count',
            'created_at',
            'updated_at',
        ]

    def get_groups_count(self, obj):
        """Return count of groups in this combo."""
        return obj.groups.count()

    def get_image_url(self, obj):
        """Return absolute URL for combo image."""
        return obj.get_image_url()


class ComboCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating StoreCombo.

    Handles basic combo info only. Groups and variant limits are managed
    separately via ComboProductGroup and ComboProductGroupVariantLimit serializers.
    """

    class Meta:
        model = StoreCombo
        fields = [
            'name',
            'slug',
            'description',
            'price',
            'compare_at_price',
            'image',
            'image_url',
            'is_active',
            'featured',
            'track_stock',
            'stock_quantity',
            'sort_order',
        ]

    def validate_price(self, value):
        """Ensure price is positive."""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value

    def validate_compare_at_price(self, value):
        """Ensure compare_at_price (if provided) is positive."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Compare at price must be greater than 0.")
        return value

    def validate(self, data):
        """Validate that compare_at_price (if set) is greater than price."""
        price = data.get('price')
        compare_at_price = data.get('compare_at_price')

        if price and compare_at_price and compare_at_price <= price:
            raise serializers.ValidationError({
                'compare_at_price': 'Compare at price must be greater than regular price.'
            })

        return data


class ComboProductGroupCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating ComboProductGroup.

    Handles group configuration (required, min/max, duplicates allowed).
    Used in pastita-dash admin UI for group management.
    """

    class Meta:
        model = ComboProductGroup
        fields = [
            'product',
            'is_required',
            'min_selections',
            'max_selections',
            'allow_duplicate_variants',
            'position',
        ]

    def validate_min_selections(self, value):
        """Ensure min_selections is non-negative."""
        if value < 0:
            raise serializers.ValidationError("Min selections must be 0 or greater.")
        return value

    def validate_max_selections(self, value):
        """Ensure max_selections is positive."""
        if value <= 0:
            raise serializers.ValidationError("Max selections must be greater than 0.")
        return value

    def validate_position(self, value):
        """Ensure position is non-negative."""
        if value < 0:
            raise serializers.ValidationError("Position must be 0 or greater.")
        return value

    def validate(self, data):
        """Validate min/max relationship and required group rules."""
        min_selections = data.get('min_selections')
        max_selections = data.get('max_selections')
        is_required = data.get('is_required')

        # Check min <= max
        if min_selections is not None and max_selections is not None:
            if min_selections > max_selections:
                raise serializers.ValidationError({
                    'min_selections': 'Min selections must be <= max selections.'
                })

        # If required, min must be > 0
        if is_required and min_selections == 0:
            raise serializers.ValidationError({
                'min_selections': 'Required groups must have min_selections > 0.'
            })

        return data


class ComboProductGroupVariantLimitCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating ComboProductGroupVariantLimit.

    Handles per-variant limits and price overrides within a group.
    Used in pastita-dash admin UI for variant configuration.
    """

    class Meta:
        model = ComboProductGroupVariantLimit
        fields = [
            'variant',
            'max_selections',
            'price_override',
        ]

    def validate_max_selections(self, value):
        """Ensure max_selections is positive."""
        if value <= 0:
            raise serializers.ValidationError("Max selections must be greater than 0.")
        return value

    def validate_price_override(self, value):
        """Ensure price_override (if provided) is non-negative."""
        if value is not None and value < 0:
            raise serializers.ValidationError("Price override must be 0 or greater.")
        return value
