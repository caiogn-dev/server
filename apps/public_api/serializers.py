"""
Public API serializers — read-only, no sensitive data exposed.
"""
from rest_framework import serializers
from apps.stores.models import Store, StoreCategory, StoreProduct, StoreCombo


class PublicStoreSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'slug', 'description', 'store_type',
            'logo_url', 'primary_color', 'secondary_color',
            'phone', 'email', 'address', 'city', 'state',
            'operating_hours', 'is_open',
        ]

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo:
            url = obj.logo.url
            return request.build_absolute_uri(url) if request else url
        return obj.logo_url or None

    def get_is_open(self, obj):
        return obj.is_open()


class PublicCategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCategory
        fields = ['id', 'name', 'slug', 'description', 'image_url', 'sort_order']

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

    class Meta:
        model = StoreProduct
        fields = [
            'id', 'name', 'slug', 'description', 'short_description',
            'price', 'compare_at_price',
            'image_url', 'category_name', 'category_slug',
            'is_available', 'sort_order',
        ]

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.main_image:
            url = obj.main_image.url
            return request.build_absolute_uri(url) if request else url
        return obj.main_image_url or None

    def get_is_available(self, obj):
        return obj.status == 'active'


class PublicComboSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCombo
        fields = ['id', 'name', 'description', 'price', 'image_url', 'is_active']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'image') and obj.image:
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return None
