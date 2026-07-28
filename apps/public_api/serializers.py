"""
Public API serializers — read-only, no sensitive data exposed.
"""
from rest_framework import serializers
from apps.stores.models import (
    Store,
    StoreCategory,
    StoreProduct,
    StoreCombo,
)
from .models import Lead


class PublicStoreSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()
    loyalty_program = serializers.SerializerMethodField()
    featured_coupon = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'slug', 'description', 'store_type',
            'logo_url', 'primary_color', 'secondary_color',
            'template', 'tagline',
            'phone', 'email', 'address', 'city', 'state',
            'operating_hours', 'is_open',
            'meta_pixel_id', 'meta_pixel_enabled',
            'clarity_id', 'clarity_enabled',
            'template', 'tagline',
            'loyalty_program', 'featured_coupon',
        ]

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo:
            url = obj.logo.url
            return request.build_absolute_uri(url) if request else url
        return obj.logo_url or None

    def get_is_open(self, obj):
        return obj.is_open()

    def get_loyalty_program(self, obj):
        from apps.stores.api.views.storefront_views import _loyalty_program_payload
        return _loyalty_program_payload(obj)

    def get_featured_coupon(self, obj):
        from apps.stores.api.views.storefront_views import _featured_coupon_payload
        return _featured_coupon_payload(obj)


class PublicCategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCategory
        fields = ['id', 'name', 'slug', 'description', 'image_url', 'sort_order', 'is_builder_group']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return obj.image_url or None


class PublicProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    image_url = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    variant_label = serializers.SerializerMethodField()

    class Meta:
        model = StoreProduct
        fields = [
            'id', 'name', 'slug', 'description', 'short_description',
            'price', 'compare_at_price',
            'image_url', 'category_name', 'category_slug',
            'is_available', 'sort_order',
            'attributes', 'tags', 'variants', 'variant_label',
        ]

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.main_image:
            url = obj.main_image.url
            return request.build_absolute_uri(url) if request else url
        return obj.main_image_url or None

    def get_is_available(self, obj):
        return obj.status == 'active'

    def get_variant_label(self, obj):
        """Retorna o label dinâmico para variantes (tamanho, sabor, ingrediente, etc)"""
        if not obj.product_type:
            return 'Opções'

        custom_fields = obj.product_type.custom_fields or []
        if custom_fields:
            first_field = custom_fields[0]
            return first_field.get('label', 'Opções')

        return 'Opções'

    def get_variants(self, obj):
        request = self.context.get('request')
        # Usa o cache do prefetch (já filtrado is_active + ordenado) quando a view
        # prefetchou 'variants'; senão cai no filtro direto (ex: product_detail).
        prefetched = getattr(obj, '_prefetched_objects_cache', {})
        if 'variants' in prefetched:
            variants = prefetched['variants']
        else:
            variants = obj.variants.filter(is_active=True).order_by('sort_order', 'name')
        data = []
        for variant in variants:
            image_url = None
            if variant.image:
                image_url = request.build_absolute_uri(variant.image.url) if request else variant.image.url
            elif variant.image_url:
                image_url = variant.image_url

            data.append({
                'id': str(variant.id),
                'name': variant.name,
                'price': variant.price,
                'compare_at_price': variant.compare_at_price,
                'image_url': image_url,
                'is_active': variant.is_active,
                'sort_order': variant.sort_order,
                'options': variant.options,
            })
        return data


class PublicComboSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()

    class Meta:
        model = StoreCombo
        fields = ['id', 'name', 'slug', 'description', 'price', 'image_url', 'is_active', 'groups']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'image') and obj.image:
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_groups(self, obj):
        """Retorna grupos com suas variantes para seleção"""
        groups_data = []
        for group in obj.groups.all():
            variant_limits = group.variant_limits.all()
            variants = []

            for limit in variant_limits:
                variant = limit.variant
                image_url = None
                if variant.image:
                    request = self.context.get('request')
                    image_url = request.build_absolute_uri(variant.image.url) if request else variant.image.url
                elif variant.image_url:
                    image_url = variant.image_url

                variants.append({
                    'variant_id': str(variant.id),
                    'name': variant.name,
                    'variant_name': variant.name,
                    'price': str(variant.price or group.product.price),
                    'price_override': str(limit.price_override) if limit.price_override else None,
                    'stock': variant.stock_quantity,
                    'max_selections': limit.max_selections,
                    'image_url': image_url,
                })

            groups_data.append({
                'id': str(group.id),
                'product_id': str(group.product.id),
                'product_name': group.product.name,
                'is_required': group.is_required,
                'min_selections': group.min_selections,
                'max_selections': group.max_selections,
                'variant_limits': variants,
            })

        return groups_data


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ['name', 'phone', 'email', 'city', 'business_type', 'message']

    def validate_phone(self, value):
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) < 10:
            raise serializers.ValidationError('Número de telefone inválido.')
        return value
