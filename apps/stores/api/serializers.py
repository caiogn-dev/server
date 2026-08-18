"""
Serializers for the stores API.
This is the UNIFIED e-commerce serializer module supporting all stores.

All product types are DYNAMIC - stores can create their own types with custom fields.
Products store type-specific values in the type_attributes JSONField.
"""
import re
import uuid as uuid_module
from decimal import Decimal, InvalidOperation
from django.db import transaction
from rest_framework import serializers
from django.utils import timezone
from apps.stores.models import (
    Store, StoreIntegration, StoreWebhook, StoreCategory,
    StoreProduct, StoreProductVariant, StoreOrder, StoreOrderItem,
    StoreCustomer, StoreWishlist, StoreProductType,
    StorePaymentGateway, StorePayment, StorePaymentWebhookEvent,
    StorePrintAgent, StorePrintJob, StoreCustomerAddress,
)
from apps.core.services.customer_identity import CustomerIdentityService


class StoreSerializer(serializers.ModelSerializer):
    """Serializer for Store model."""
    
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()
    integrations_count = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()
    orders_count = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'slug', 'description', 'store_type', 'status',
            'logo', 'logo_url', 'banner', 'banner_url',
            'primary_color', 'secondary_color',
            'template', 'tagline', 'custom_domain',
            'email', 'phone', 'whatsapp_number',
            'address', 'city', 'state', 'zip_code', 'country',
            'latitude', 'longitude',
            'currency', 'timezone', 'tax_rate',
            'delivery_enabled', 'pickup_enabled',
            'min_order_value', 'free_delivery_threshold', 'default_delivery_fee',
            'operating_hours', 'is_open',
            'avg_rating', 'reviews_count',
            'owner', 'metadata',
            'meta_pixel_id', 'meta_pixel_enabled',
            'clarity_id', 'clarity_enabled',
            'plan', 'trial_ends_at', 'onboarding_completed',
            # A aba Recebimento precisa distinguir "loja do dono, recebe na conta
            # da plataforma" de "loja de cliente sem conta cadastrada". Sem isto
            # a tela mostrava alerta de "sem conta" para loja que recebe normal.
            'usa_gateway_da_plataforma',
            'integrations_count', 'products_count', 'orders_count',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at',
                            'plan', 'trial_ends_at']


    # Estes 5 contadores são anotados na queryset do StoreViewSet (anno_*) via
    # Subquery — 1 query em vez de 5 por loja. Se a anotação não estiver
    # presente (ex: serializer usado fora do viewset), cai no fallback antigo.
    def get_avg_rating(self, obj):
        if hasattr(obj, 'anno_avg_rating'):
            v = obj.anno_avg_rating
            return round(v, 1) if v is not None else None
        from django.db.models import Avg
        avg = obj.reviews.filter(is_public=True).aggregate(a=Avg('rating'))['a']
        return round(avg, 1) if avg is not None else None

    def get_reviews_count(self, obj):
        if hasattr(obj, 'anno_reviews_count'):
            return obj.anno_reviews_count
        return obj.reviews.filter(is_public=True).count()

    def get_logo_url(self, obj):
        return obj.get_logo_url()

    def get_banner_url(self, obj):
        return obj.get_banner_url()

    def get_is_open(self, obj):
        return obj.is_open()

    def get_integrations_count(self, obj):
        if hasattr(obj, 'anno_integrations_count'):
            return obj.anno_integrations_count
        return obj.integrations.filter(is_active=True).count()

    def get_products_count(self, obj):
        if hasattr(obj, 'anno_products_count'):
            return obj.anno_products_count
        return obj.products.filter(status='active').count()

    def get_orders_count(self, obj):
        if hasattr(obj, 'anno_orders_count'):
            return obj.anno_orders_count
        return obj.orders.count()


class StoreMetaTrackingSerializer(serializers.ModelSerializer):
    """Owner-facing Meta configuration without leaking the stored CAPI token."""

    meta_capi_access_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=True,
    )
    meta_capi_token_configured = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'meta_pixel_id', 'meta_pixel_enabled',
            'meta_capi_enabled', 'meta_capi_access_token',
            'meta_capi_token_configured', 'meta_capi_test_event_code',
            'clarity_id', 'clarity_enabled',
        ]

    def get_meta_capi_token_configured(self, obj):
        return bool(obj.meta_capi_access_token)

    def validate_meta_pixel_id(self, value):
        value = value.strip()
        if value and not value.isdigit():
            raise serializers.ValidationError('Informe somente os números do ID do Pixel.')
        return value

    def validate_clarity_id(self, value):
        value = value.strip()
        if value and not re.fullmatch(r'[a-z0-9]{4,32}', value, re.IGNORECASE):
            raise serializers.ValidationError('ID do Clarity inválido — use o código do projeto (letras e números).')
        return value

    def validate(self, attrs):
        pixel_id = attrs.get('meta_pixel_id', self.instance.meta_pixel_id)
        pixel_enabled = attrs.get('meta_pixel_enabled', self.instance.meta_pixel_enabled)
        capi_enabled = attrs.get('meta_capi_enabled', self.instance.meta_capi_enabled)
        token = attrs.get('meta_capi_access_token', self.instance.meta_capi_access_token)
        if (pixel_enabled or capi_enabled) and not pixel_id:
            raise serializers.ValidationError({'meta_pixel_id': 'Informe o ID do Pixel antes de ativar.'})
        if capi_enabled and not token:
            raise serializers.ValidationError({'meta_capi_access_token': 'Informe o token da Conversions API antes de ativar.'})
        clarity_id = attrs.get('clarity_id', self.instance.clarity_id)
        clarity_enabled = attrs.get('clarity_enabled', self.instance.clarity_enabled)
        if clarity_enabled and not clarity_id:
            raise serializers.ValidationError({'clarity_id': 'Informe o ID do Clarity antes de ativar.'})
        return attrs

    def update(self, instance, validated_data):
        if validated_data.get('meta_capi_access_token') == '':
            validated_data.pop('meta_capi_access_token')
        return super().update(instance, validated_data)


class StoreCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new store."""
    
    class Meta:
        model = Store
        fields = [
            'name', 'slug', 'description', 'store_type',
            'email', 'phone', 'whatsapp_number',
            'address', 'city', 'state', 'zip_code',
            'currency', 'timezone',
            'delivery_enabled', 'pickup_enabled',
            'min_order_value', 'default_delivery_fee'
        ]
    
    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class StoreIntegrationSerializer(serializers.ModelSerializer):
    """Serializer for StoreIntegration model."""
    
    masked_api_key = serializers.ReadOnlyField()
    masked_access_token = serializers.ReadOnlyField()
    integration_type_display = serializers.CharField(source='get_integration_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = StoreIntegration
        fields = [
            'id', 'store', 'integration_type', 'integration_type_display',
            'name', 'status', 'status_display',
            'masked_api_key', 'masked_access_token',
            'external_id', 'phone_number_id', 'waba_id',
            'webhook_url', 'webhook_verify_token',
            'settings', 'token_expires_at',
            'last_error', 'last_error_at',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_error', 'last_error_at']


class StoreIntegrationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating integrations with credentials."""

    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    access_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    refresh_token = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = StoreIntegration
        fields = [
            'store', 'integration_type', 'name',
            'api_key', 'api_secret', 'access_token', 'refresh_token',
            'external_id', 'phone_number_id', 'waba_id',
            'webhook_url', 'webhook_secret', 'webhook_verify_token',
            'settings'
        ]

    def validate_store(self, value):
        """Bloqueia acesso cross-tenant: apenas superuser pode usar qualquer loja."""
        from apps.core.permissions import user_can_access_store
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            if not user_can_access_store(request.user, value):
                raise serializers.ValidationError('Loja não encontrada')
        return value

    def create(self, validated_data):
        # Extract credential fields
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)
        access_token = validated_data.pop('access_token', None)
        refresh_token = validated_data.pop('refresh_token', None)
        
        integration = StoreIntegration(**validated_data)
        
        # Set encrypted credentials
        if api_key:
            integration.api_key = api_key
        if api_secret:
            integration.api_secret = api_secret
        if access_token:
            integration.access_token = access_token
        if refresh_token:
            integration.refresh_token = refresh_token
        
        integration.status = StoreIntegration.IntegrationStatus.ACTIVE
        integration.save()
        return integration
    
    def update(self, instance, validated_data):
        # Extract credential fields
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)
        access_token = validated_data.pop('access_token', None)
        refresh_token = validated_data.pop('refresh_token', None)
        
        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update encrypted credentials only if provided
        if api_key:
            instance.api_key = api_key
        if api_secret:
            instance.api_secret = api_secret
        if access_token:
            instance.access_token = access_token
        if refresh_token:
            instance.refresh_token = refresh_token
        
        instance.save()
        return instance


class StoreWebhookSerializer(serializers.ModelSerializer):
    """Serializer for StoreWebhook model."""

    def validate_url(self, value):
        # Guard anti-SSRF: o backend chama essa URL server-side depois.
        from django.core.exceptions import ValidationError as DjangoValidationError
        from apps.core.url_security import validate_public_webhook_url
        try:
            return validate_public_webhook_url(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))

    def validate_store(self, value):
        """Bloqueia acesso cross-tenant: apenas superuser pode usar qualquer loja."""
        from apps.core.permissions import user_can_access_store
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            if not user_can_access_store(request.user, value):
                raise serializers.ValidationError('Loja não encontrada')
        return value

    class Meta:
        model = StoreWebhook
        fields = [
            'id', 'store', 'name', 'url', 'secret', 'events',
            'headers', 'max_retries', 'retry_delay',
            'total_calls', 'successful_calls', 'failed_calls',
            'last_called_at', 'last_success_at', 'last_failure_at', 'last_error',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'total_calls', 'successful_calls', 'failed_calls',
            'last_called_at', 'last_success_at', 'last_failure_at', 'last_error',
            'created_at', 'updated_at'
        ]


class StoreCategorySerializer(serializers.ModelSerializer):
    """Serializer for StoreCategory model."""
    
    image_url = serializers.URLField(required=False, allow_blank=True)
    products_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCategory
        fields = [
            'id', 'store', 'name', 'slug', 'description',
            'image', 'image_url', 'parent', 'children',
            'sort_order', 'is_active', 'is_builder_group', 'products_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        return obj.get_image_url()
    
    def get_products_count(self, obj):
        # Lê a annotation do viewset (1 query no JOIN) p/ não contar por categoria.
        anno = getattr(obj, 'anno_products_count', None)
        if anno is not None:
            return anno
        return obj.products.filter(status='active').count()

    def get_children(self, obj):
        # Usa o Prefetch('children', is_active) do viewset quando presente (sem query
        # por linha); fallback p/ a query direta fora do contexto do viewset.
        if 'children' in getattr(obj, '_prefetched_objects_cache', {}):
            children = obj.children.all()
        else:
            children = obj.children.filter(is_active=True)
        return StoreCategorySerializer(children, many=True).data


class StoreProductVariantSerializer(serializers.ModelSerializer):
    """Serializer for StoreProductVariant model."""
    
    effective_price = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreProductVariant
        fields = [
            'id', 'product', 'name', 'sku', 'barcode',
            'price', 'compare_at_price', 'effective_price',
            'stock_quantity', 'options',
            'image', 'image_url',
            'is_active', 'sort_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_effective_price(self, obj):
        return str(obj.get_price())
    
    def get_image_url(self, obj):
        return obj.get_image_url()


class StoreProductSerializer(serializers.ModelSerializer):
    """Serializer for StoreProduct model with dynamic product type support."""
    
    main_image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    product_type_name = serializers.CharField(source='product_type.name', read_only=True)
    product_type_slug = serializers.CharField(source='product_type.slug', read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    is_paused = serializers.ReadOnlyField()
    variants = StoreProductVariantSerializer(many=True, read_only=True)
    catalog_role = serializers.SerializerMethodField()
    merchandising_flags = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    class Meta:
        model = StoreProduct
        fields = [
            'id', 'store', 'category', 'category_name', 'category_slug',
            'product_type', 'product_type_name', 'product_type_slug', 'type_attributes',
            'name', 'slug', 'description', 'short_description',
            'sku', 'barcode',
            'price', 'compare_at_price', 'cost_price',
            # Promoção que se repete toda semana ("quarta da almôndega"). O
            # `price` NUNCA é alterado: `preco_vigente()` decide na leitura.
            # Sem estes campos aqui o recurso existia no model e no cálculo mas
            # não tinha como ser cadastrado por ninguém.
            'promo_price', 'promo_weekday',
            'is_on_sale', 'discount_percentage',
            'track_stock', 'stock_quantity', 'low_stock_threshold',
            'allow_backorder', 'is_low_stock', 'is_in_stock',
            'paused_until', 'is_paused',
            'status', 'featured',
            'main_image', 'main_image_url', 'images',
            'meta_title', 'meta_description',
            'weight', 'weight_unit', 'dimensions',
            'attributes', 'tags', 'sort_order',
            'catalog_role', 'merchandising_flags',
            'rating_avg', 'rating_count',
            'view_count', 'sold_count',
            'variants',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'view_count', 'sold_count', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        return obj.get_main_image_url()

    # Média/contagem de avaliações por produto. SÓ via annotation (anno_rating_*,
    # feita na queryset do catálogo) — sem fallback com query pra não criar N+1
    # nos outros usos deste serializer (dash, wishlist etc.).
    def get_rating_avg(self, obj):
        v = getattr(obj, 'anno_rating_avg', None)
        return round(v, 1) if v is not None else None

    def get_rating_count(self, obj):
        return getattr(obj, 'anno_rating_count', 0) or 0

    def get_catalog_role(self, obj):
        category_slug = (obj.category.slug if obj.category else '').lower()
        tags = {str(tag).lower() for tag in (obj.tags or [])}
        if category_slug in {'mais-pedidos', 'promocoes'} or obj.featured:
            return 'featured'
        if category_slug in {'bebidas', 'molhos'} or tags & {'upsell', 'cross-sell', 'cross_sell', 'bebida', 'molho'}:
            return 'addon'
        return 'primary'

    def get_merchandising_flags(self, obj):
        category_slug = (obj.category.slug if obj.category else '').lower()
        tags = {str(tag).lower() for tag in (obj.tags or [])}
        return {
            'is_featured': bool(obj.featured or category_slug in {'mais-pedidos', 'promocoes'} or 'destaque' in tags),
            'is_upsell': bool(category_slug in {'bebidas', 'molhos'} or tags & {'upsell', 'adicional'}),
            'is_cross_sell': bool(tags & {'cross-sell', 'cross_sell', 'combo'} or category_slug in {'bebidas', 'molhos'}),
            'category_slug': category_slug,
            'product_type_slug': obj.product_type.slug if obj.product_type else '',
        }


class StoreProductCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products with dynamic product type support."""
    
    class Meta:
        model = StoreProduct
        fields = [
            'store', 'category', 'product_type', 'type_attributes',
            'name', 'slug', 'description', 'short_description',
            'sku', 'barcode', 'price', 'compare_at_price', 'cost_price',
            'track_stock', 'stock_quantity', 'low_stock_threshold', 'allow_backorder',
            'status', 'featured', 'main_image', 'main_image_url', 'images',
            'meta_title', 'meta_description',
            'weight', 'weight_unit', 'dimensions',
            'attributes', 'tags', 'sort_order'
        ]
    
    def validate(self, data):
        """Validate type_attributes against product_type custom_fields."""
        product_type = data.get('product_type')
        type_attributes = data.get('type_attributes', {})
        
        if product_type and product_type.custom_fields:
            for field_def in product_type.custom_fields:
                field_name = field_def.get('name')
                is_required = field_def.get('required', False)
                
                if is_required and field_name not in type_attributes:
                    raise serializers.ValidationError({
                        'type_attributes': f"Field '{field_name}' is required for product type '{product_type.name}'"
                    })
        
        return data


# =============================================================================
# DYNAMIC PRODUCT TYPE SERIALIZERS
# =============================================================================

class StoreProductTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for dynamic product types.
    
    Product types define custom fields that products of this type should have.
    The custom_fields JSONField contains field definitions like:
    [
        {"name": "tipo", "label": "Tipo", "type": "select", "options": [{"value": "4queijos", "label": "4 Queijos"}], "required": true},
        {"name": "quantidade", "label": "Quantidade", "type": "text", "required": true},
        {"name": "calorias", "label": "Calorias", "type": "number", "required": false}
    ]
    """
    products_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreProductType
        fields = [
            'id', 'store', 'name', 'slug', 'description',
            'icon', 'image', 'custom_fields',
            'sort_order', 'is_active', 'show_in_menu',
            'products_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_products_count(self, obj):
        return obj.products.filter(status='active').count()


class StoreProductTypeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating product types."""
    
    class Meta:
        model = StoreProductType
        fields = [
            'store', 'name', 'slug', 'description',
            'icon', 'image', 'custom_fields',
            'sort_order', 'is_active', 'show_in_menu'
        ]


class StoreProductWithTypeSerializer(serializers.ModelSerializer):
    """
    Product serializer that includes dynamic product type info.
    
    The type_attributes field contains values for custom fields defined by the product_type.
    """
    main_image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    product_type_info = StoreProductTypeSerializer(source='product_type', read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    is_paused = serializers.ReadOnlyField()
    variants = StoreProductVariantSerializer(many=True, read_only=True)
    
    class Meta:
        model = StoreProduct
        fields = [
            'id', 'store', 'category', 'category_name',
            'product_type', 'product_type_info', 'type_attributes',
            'name', 'slug', 'description', 'short_description',
            'sku', 'barcode',
            'price', 'compare_at_price', 'cost_price',
            'is_on_sale', 'discount_percentage',
            'track_stock', 'stock_quantity', 'low_stock_threshold',
            'allow_backorder', 'is_low_stock', 'is_in_stock',
            'paused_until', 'is_paused',
            'status', 'featured',
            'main_image', 'main_image_url', 'images',
            'attributes', 'tags', 'sort_order',
            'variants',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_main_image_url(self, obj):
        return obj.get_main_image_url()


# =============================================================================
# WISHLIST SERIALIZERS
# =============================================================================

class StoreWishlistSerializer(serializers.ModelSerializer):
    """Serializer for user wishlist."""
    
    products = StoreProductSerializer(many=True, read_only=True)
    products_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreWishlist
        fields = ['id', 'store', 'user', 'products', 'products_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def get_products_count(self, obj):
        return obj.products.count()


class WishlistAddRemoveSerializer(serializers.Serializer):
    """Serializer for adding/removing products from wishlist."""
    
    product_id = serializers.UUIDField()


class StoreOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for StoreOrderItem model."""
    
    class Meta:
        model = StoreOrderItem
        fields = [
            'id', 'product', 'variant',
            'product_name', 'variant_name', 'sku',
            'unit_price', 'quantity', 'subtotal',
            'options', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'subtotal', 'created_at']


class StoreOrderSerializer(serializers.ModelSerializer):
    """Serializer for StoreOrder model."""
    
    items = StoreOrderItemSerializer(many=True, read_only=True)
    combo_items = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    delivery_method_display = serializers.CharField(source='get_delivery_method_display', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    store_slug = serializers.CharField(source='store.slug', read_only=True)
    items_count = serializers.SerializerMethodField()
    # Fase 3 — derivados da soma dos StorePayment 'completed' (read-only).
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    amount_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)

    class Meta:
        model = StoreOrder
        fields = [
            'id', 'store', 'store_name', 'store_slug', 'order_number', 'access_token',
            'customer', 'customer_name', 'customer_email', 'customer_phone',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'subtotal', 'discount', 'coupon_code', 'tax', 'delivery_fee', 'total',
            'amount_paid', 'amount_due', 'is_fully_paid',
            'surcharge_value', 'surcharge_reason',
            'manual_discount_value', 'manual_discount_type', 'manual_discount_reason',
            'payment_method', 'payment_id', 'payment_preference_id',
            'pix_code', 'pix_qr_code', 'pix_ticket_url', 'pix_expires_at',
            'delivery_method', 'delivery_method_display',
            'delivery_address', 'delivery_notes',
            'scheduled_date', 'scheduled_time',
            'tracking_code', 'tracking_url', 'carrier',
            'customer_notes', 'internal_notes',
            'paid_at', 'confirmed_at', 'preparing_at', 'processing_at',
            'ready_at', 'out_for_delivery_at', 'shipped_at',
            'delivered_at', 'picked_up_at', 'cancelled_at',
            'items', 'combo_items', 'items_count', 'metadata',
            # `source` é o canal de origem (web/whatsapp/pdv). O resumo do
            # histórico já quebrava a receita por canal, mas a coluna da lista
            # mostrava "—" porque o serializer nunca expôs o campo — dois
            # números da mesma tela discordando sobre o mesmo pedido.
            'source',
            'created_at', 'updated_at', 'is_active',
            'delivery_provider',
            'uber_delivery_request_id', 'uber_driver_id', 'uber_driver_name',
            'uber_driver_phone', 'uber_vehicle_info', 'uber_eta_minutes',
            'uber_pickup_instructions', 'uber_created_at',
        ]
        read_only_fields = [
            'id', 'order_number', 'access_token', 'created_at', 'updated_at',
            'source',
            'paid_at', 'confirmed_at', 'preparing_at', 'processing_at',
            'ready_at', 'out_for_delivery_at', 'shipped_at',
            'delivered_at', 'picked_up_at', 'cancelled_at',
            'uber_delivery_request_id', 'uber_driver_id', 'uber_driver_name',
            'uber_driver_phone', 'uber_vehicle_info', 'uber_eta_minutes',
            'uber_pickup_instructions', 'uber_created_at',
            'surcharge_value', 'surcharge_reason',
            'manual_discount_value', 'manual_discount_type', 'manual_discount_reason',
        ]
    
    def get_items_count(self, obj):
        return len(obj.items.all())

    def get_combo_items(self, obj):
        return StoreOrderComboItemSerializer(obj.combo_items.all(), many=True).data


class StorePrintAgentSerializer(serializers.ModelSerializer):
    """Serializer for local print agents."""

    is_online = serializers.SerializerMethodField()

    class Meta:
        model = StorePrintAgent
        fields = [
            'id', 'store', 'name', 'slug', 'status', 'station',
            'platform', 'connection_mode', 'printer_name', 'printer_host',
            'printer_port', 'poll_interval_seconds', 'max_retries',
            'last_seen_at', 'last_seen_ip', 'last_error',
            'app_version', 'host_name', 'available_printers', 'metadata', 'is_online',
            'created_at', 'updated_at', 'is_active',
        ]
        read_only_fields = [
            'id', 'last_seen_at', 'last_seen_ip', 'last_error',
            'app_version', 'host_name', 'created_at', 'updated_at',
        ]

    def get_is_online(self, obj):
        if not obj.last_seen_at:
            return False
        return (timezone.now() - obj.last_seen_at).total_seconds() <= (obj.poll_interval_seconds * 4)


class StorePrintAgentCreateSerializer(serializers.ModelSerializer):
    """Create serializer that returns the one-time raw API key."""

    api_key = serializers.CharField(read_only=True)

    class Meta:
        model = StorePrintAgent
        fields = [
            'id', 'store', 'name', 'slug', 'status', 'station',
            'platform', 'connection_mode', 'printer_name', 'printer_host',
            'printer_port', 'poll_interval_seconds', 'max_retries',
            'metadata', 'api_key', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'api_key', 'created_at', 'updated_at']

    def validate_store(self, value):
        """Bloqueia acesso cross-tenant: apenas superuser pode usar qualquer loja."""
        from apps.core.permissions import user_can_access_store
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            if not user_can_access_store(request.user, value):
                raise serializers.ValidationError('Loja não encontrada')
        return value

    def create(self, validated_data):
        raw_key, prefix, hashed = StorePrintAgent.generate_api_key()
        agent = StorePrintAgent.objects.create(
            api_key_prefix=prefix,
            api_key_hash=hashed,
            **validated_data,
        )
        agent._raw_api_key = raw_key
        return agent

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['api_key'] = getattr(instance, '_raw_api_key', '')
        return data


class StorePrintJobSerializer(serializers.ModelSerializer):
    """Serializer for print jobs."""

    store_name = serializers.CharField(source='store.name', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    claimed_by_name = serializers.CharField(source='claimed_by.name', read_only=True)
    target_agent_name = serializers.CharField(source='target_agent.name', read_only=True)

    class Meta:
        model = StorePrintJob
        fields = [
            'id', 'store', 'store_name', 'order', 'order_number',
            'status', 'station', 'template', 'source', 'title',
            'payload', 'dedupe_key', 'claimed_by', 'claimed_by_name',
            'target_agent', 'target_agent_name',
            'claimed_at', 'printed_at', 'failed_at', 'available_at',
            'attempts', 'max_attempts', 'last_error', 'printer_name',
            'metadata', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class StoreOrderCreateItemSerializer(serializers.Serializer):
    """Line item payload for order creation."""

    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    options = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class StoreOrderCreateSerializer(serializers.Serializer):
    """Serializer for creating orders."""

    store = serializers.CharField(required=False)
    customer_name = serializers.CharField(max_length=255)
    # allow_null: o PDV manda null quando o cliente selecionado (ex.: cadastrado
    # em outra loja) não tem email — o fallback @local.invalid cobre depois
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(max_length=20)
    customer_notes = serializers.CharField(required=False, allow_blank=True)

    items = StoreOrderCreateItemSerializer(many=True, min_length=1)

    delivery_method = serializers.ChoiceField(
        choices=['delivery', 'pickup', 'digital'],
        default='delivery'
    )
    delivery_address = serializers.JSONField(required=False, default=dict)
    delivery_notes = serializers.CharField(required=False, allow_blank=True)
    delivery_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
    )
    scheduled_date = serializers.DateField(required=False)
    scheduled_time = serializers.CharField(required=False, allow_blank=True)

    payment_method = serializers.CharField(required=False, allow_blank=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    discount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
    )
    surcharge = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
    )
    adjustment_reason = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    # Canal de origem da venda. Quem sabe disso é o cliente da API — o mesmo
    # endpoint serve o PDV Balcão, o drawer de pedido manual e integrações.
    # Sem ninguém dizer, o `save()` do model cai em 'web' e o relatório por
    # canal creditava o SITE por toda venda de balcão (medido em 15/ago).
    # A tradução para a coluna é do model (`_SOURCE_MAP_PREFIXES`): valor
    # desconhecido vira 'web' em vez de sujar o BI com string livre.
    source = serializers.CharField(required=False, allow_blank=True)
    # Pedido de balcão: não enviar nenhuma mensagem automática de status
    suppress_notifications = serializers.BooleanField(required=False)
    # Balcão: além da comanda da cozinha, imprimir cupom do cliente
    # (template customer_receipt) na estação 'balcao'
    print_receipt = serializers.BooleanField(required=False)

    def _resolve_store(self, validated_data):
        """Resolve store from payload, query params, or nested router kwargs."""
        import re
        request = self.context.get('request')
        view = self.context.get('view')

        store_param = validated_data.get('store')
        if not store_param and view:
            store_param = view.kwargs.get('store_pk')
        if not store_param and request:
            store_param = request.query_params.get('store')

        # Fallback: extract store slug from request path/URL
        if not store_param and request:
            # Try multiple path sources
            path = getattr(request, 'path', '') or str(request.build_absolute_uri())
            # Extract store slug from URL patterns like /api/v1/stores/{slug}/orders/
            match = re.search(r'/stores/([^/]+?)(?:/|$)', path)
            if match:
                store_param = match.group(1)

        if not store_param:
            raise serializers.ValidationError({'store': 'store is required'})

        try:
            uuid_module.UUID(str(store_param))
            store = Store.objects.filter(id=store_param).first()
        except (ValueError, AttributeError):
            store = Store.objects.filter(slug=str(store_param)).first()

        if not store:
            raise serializers.ValidationError({'store': 'Store not found'})

        if request and request.user.is_authenticated and not request.user.is_superuser:
            has_access = (
                store.owner_id == request.user.id
                or store.staff.filter(id=request.user.id).exists()
            )
            if not has_access:
                raise serializers.ValidationError({'store': 'No access to this store'})

        return store

    @transaction.atomic
    def create(self, validated_data):
        store = self._resolve_store(validated_data)
        request = self.context.get('request')
        items_data = validated_data.pop('items', [])
        validated_data.pop('store', None)

        subtotal = Decimal('0.00')
        resolved_items = []

        for idx, item in enumerate(items_data):
            product = StoreProduct.objects.filter(
                id=item['product_id'],
                store=store,
                status=StoreProduct.ProductStatus.ACTIVE,
            ).first()
            if not product:
                raise serializers.ValidationError({
                    'items': f'Product not found for item index {idx}'
                })

            quantity = item.get('quantity', 1)
            unit_price = product.price or Decimal('0.00')
            line_subtotal = unit_price * quantity
            subtotal += line_subtotal

            resolved_items.append({
                'product': product,
                'quantity': quantity,
                'unit_price': unit_price,
                'subtotal': line_subtotal,
                'options': item.get('options', {}),
                'notes': item.get('notes', ''),
            })

        delivery_fee = validated_data.get('delivery_fee', Decimal('0.00'))
        try:
            delivery_fee = Decimal(str(delivery_fee))
        except (ValueError, InvalidOperation):
            delivery_fee = Decimal('0.00')

        discount = validated_data.get('discount', Decimal('0.00'))
        surcharge = validated_data.get('surcharge', Decimal('0.00'))
        try:
            discount = max(Decimal('0.00'), Decimal(str(discount)))
        except (ValueError, InvalidOperation):
            discount = Decimal('0.00')
        try:
            surcharge = max(Decimal('0.00'), Decimal(str(surcharge)))
        except (ValueError, InvalidOperation):
            surcharge = Decimal('0.00')

        tax = Decimal('0.00')
        total = subtotal - discount + tax + delivery_fee + surcharge
        if total < Decimal('0.00'):
            raise serializers.ValidationError({
                'discount': 'Discount cannot make order total negative'
            })

        delivery_address = validated_data.get('delivery_address', {})
        if isinstance(delivery_address, str):
            delivery_address = {'address': delivery_address}

        customer_email = (validated_data.get('customer_email') or '').strip()
        if not customer_email:
            digits = ''.join(ch for ch in validated_data.get('customer_phone', '') if ch.isdigit())
            suffix = digits[-8:] if digits else 'cliente'
            customer_email = f'{suffix}@local.invalid'

        metadata = {}
        # Guardado CRU: 'dashboard' e 'pdv' viram a mesma coluna, e sem o
        # original não dá para distinguir os dois depois.
        canal = (validated_data.get('source') or '').strip()
        if canal:
            metadata['source'] = canal
        if validated_data.get('suppress_notifications'):
            metadata['suppress_notifications'] = True
        adjustment_reason = (validated_data.get('adjustment_reason') or '').strip()
        if 'delivery_fee' in validated_data:
            metadata['manual_delivery_fee'] = {
                'amount': str(delivery_fee),
                'reason': adjustment_reason,
                'source': 'dashboard_order_create',
                'user_id': str(request.user.id) if request and request.user.is_authenticated else '',
            }
        if surcharge > 0:
            metadata['manual_surcharge'] = str(surcharge)
        if discount > 0 or surcharge > 0 or adjustment_reason:
            metadata['manual_adjustment'] = {
                'discount': str(discount),
                'surcharge': str(surcharge),
                'reason': adjustment_reason,
            }

        customer_record = CustomerIdentityService.sync_checkout_customer(
            store=store,
            customer_name=validated_data['customer_name'],
            email=customer_email,
            phone=validated_data['customer_phone'],
            delivery_method=validated_data.get('delivery_method', 'delivery'),
            delivery_address=delivery_address,
        )
        customer_user = customer_record.get('user')
        store_customer = customer_record.get('store_customer')

        if store_customer:
            metadata['customer'] = {
                'user_id': str(customer_user.id) if customer_user else '',
                'store_customer_id': str(store_customer.id),
                'source': 'dashboard_order_create',
            }

        order = StoreOrder.objects.create(
            store=store,
            customer=customer_user,
            customer_name=validated_data['customer_name'],
            customer_email=customer_email,
            customer_phone=validated_data['customer_phone'],
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            subtotal=subtotal,
            discount=discount,
            coupon_code=validated_data.get('coupon_code', ''),
            tax=tax,
            delivery_fee=delivery_fee,
            total=total,
            payment_method=validated_data.get('payment_method', ''),
            delivery_method=validated_data.get('delivery_method', 'delivery'),
            delivery_address=delivery_address,
            delivery_notes=validated_data.get('delivery_notes', ''),
            scheduled_date=validated_data.get('scheduled_date'),
            scheduled_time=validated_data.get('scheduled_time', ''),
            customer_notes=validated_data.get('customer_notes') or validated_data.get('notes', ''),
            metadata=metadata,
        )

        # Trava e valida o estoque ANTES de decrementar. Este caminho (PDV/painel)
        # só tinha copiado o UPDATE com F() do storefront, não a validação com
        # lock que vem antes dele — então uma venda de balcão de 5 unidades num
        # produto com 2 levava stock_quantity a -3 em silêncio (o campo é
        # IntegerField, sem piso). A partir daí `is_in_stock` vira False e o item
        # some do cardápio web E do bot, e a reposição parte do número negativo.
        # O select_for_update também fecha a corrida com um checkout web em voo.
        agrupado = {}
        for item in resolved_items:
            if item['product'].track_stock:
                agrupado[item['product'].id] = agrupado.get(item['product'].id, 0) + item['quantity']
        if agrupado:
            travados = {
                p.id: p
                for p in StoreProduct.objects.select_for_update().filter(id__in=list(agrupado))
            }
            for pid, qtd in agrupado.items():
                p = travados.get(pid)
                if p and not p.allow_backorder and p.stock_quantity < qtd:
                    raise serializers.ValidationError({
                        'items': f'Estoque insuficiente de {p.name}: '
                                 f'disponível {p.stock_quantity}, pedido {qtd}'
                    })

        stock_changed = False
        for item in resolved_items:
            StoreOrderItem.objects.create(
                order=order,
                product=item['product'],
                variant=None,
                product_name=item['product'].name,
                variant_name='',
                sku=item['product'].sku,
                unit_price=item['unit_price'],
                quantity=item['quantity'],
                subtotal=item['subtotal'],
                options=item['options'],
                notes=item['notes'],
            )

            # Baixa de estoque — mesmo comportamento do checkout do storefront
            # (checkout_service). Sem isso, venda de balcão/PDV não dava baixa.
            if item['product'].track_stock:
                from django.db.models import F
                StoreProduct.objects.filter(id=item['product'].id).update(
                    stock_quantity=F('stock_quantity') - item['quantity'],
                    sold_count=F('sold_count') + item['quantity'],
                )
                stock_changed = True

        if stock_changed:
            from apps.stores.services.checkout_service import _invalidate_agent_menu_safe
            store_id = order.store_id
            transaction.on_commit(lambda: _invalidate_agent_menu_safe(store_id))

        from apps.stores.services.print_service import enqueue_order_print_job
        transaction.on_commit(
            lambda order_id=order.id: enqueue_order_print_job(
                StoreOrder.objects.get(id=order_id)
            )
        )

        if validated_data.get('print_receipt'):
            from apps.stores.models.printing import StorePrintJob
            transaction.on_commit(
                lambda order_id=order.id: enqueue_order_print_job(
                    StoreOrder.objects.get(id=order_id),
                    station='balcao',
                    template=StorePrintJob.Template.CUSTOMER_RECEIPT,
                )
            )

        return order


class StoreOrderUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualizar status + dados editáveis do pedido (sem itens)."""

    # Silencia as notificações automáticas de WhatsApp deste pedido (balcão).
    # Gravado em metadata para não exigir migração nem expor metadata inteiro
    # à escrita (clobber de manual_payment etc.).
    suppress_notifications = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = StoreOrder
        fields = [
            'status', 'payment_status', 'internal_notes',
            'tracking_code', 'tracking_url', 'carrier',
            # Fase 2 — agendamento + dados do pedido (sem itens/total)
            'scheduled_date', 'scheduled_time',
            'customer_name', 'customer_phone', 'delivery_address', 'customer_notes',
            'suppress_notifications',
        ]
        extra_kwargs = {
            'scheduled_date': {'required': False, 'allow_null': True},
            'scheduled_time': {'required': False, 'allow_blank': True},
            'customer_name': {'required': False},
            'customer_phone': {'required': False},
            # M-2: aceitar null explícito sem 400; M-1: rejeitar não-dicionário
            'delivery_address': {'required': False, 'allow_null': True},
            'customer_notes': {'required': False, 'allow_blank': True},
        }

    def validate_delivery_address(self, value):
        """M-1+M-2: null vira {}; não-dicionário é rejeitado com 400."""
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                'delivery_address deve ser um objeto JSON (dicionário), não um valor escalar.'
            )
        return value

    def update(self, instance, validated_data):
        suppress = validated_data.pop('suppress_notifications', None)
        if suppress is not None:
            metadata = instance.metadata if isinstance(instance.metadata, dict) else {}
            metadata['suppress_notifications'] = suppress
            instance.metadata = metadata
        return super().update(instance, validated_data)


class StoreOrderItemOpSerializer(serializers.Serializer):
    """Uma operação sobre itens do pedido na edição."""
    op = serializers.ChoiceField(choices=['add', 'update', 'remove'])
    item_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False)
    quantity = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        op = attrs['op']
        if op == 'add' and not attrs.get('product_id'):
            raise serializers.ValidationError("op 'add' exige product_id.")
        if op in ('update', 'remove') and not attrs.get('item_id'):
            raise serializers.ValidationError(f"op '{op}' exige item_id.")
        if op in ('add', 'update') and not attrs.get('quantity'):
            raise serializers.ValidationError(f"op '{op}' exige quantity.")
        return attrs


class StoreOrderAdjustSerializer(serializers.Serializer):
    """Valida o corpo do POST /orders/{id}/adjust/ (todos os campos opcionais)."""
    discount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal('0.00'))
    discount_reason = serializers.CharField(required=False, allow_blank=True)
    surcharge_value = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, min_value=Decimal('0.00'))
    surcharge_reason = serializers.CharField(required=False, allow_blank=True)
    delivery_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal('0.00'))
    item_ops = StoreOrderItemOpSerializer(many=True, required=False)


class StoreCustomerAddressSerializer(serializers.ModelSerializer):
    """Endereço relacional do cliente (StoreCustomerAddress)."""
    id = serializers.UUIDField(required=False)

    class Meta:
        model = StoreCustomerAddress
        fields = [
            'id', 'label', 'street', 'number', 'complement',
            'neighborhood', 'city', 'state', 'zip_code', 'reference', 'is_default',
        ]


class StoreCustomerSerializer(serializers.ModelSerializer):
    """Serializer do StoreCustomer. `name` é gravável e resolve o auth.User."""

    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    default_address = serializers.SerializerMethodField()
    name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    address_list = StoreCustomerAddressSerializer(many=True, required=False)

    class Meta:
        model = StoreCustomer
        fields = [
            'id', 'store', 'user', 'user_email', 'user_name', 'name',
            'phone', 'whatsapp',
            'instagram', 'twitter', 'facebook',
            'addresses', 'default_address_index', 'default_address',
            'address_list',
            'total_orders', 'total_spent', 'last_order_at',
            'gasto_real', 'pedidos_reais', 'dias_sem_comprar', 'perfil',
            'tags', 'notes',
            'accepts_marketing', 'marketing_opt_in_at',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'store', 'user', 'total_orders', 'total_spent', 'last_order_at',
            'gasto_real', 'pedidos_reais', 'dias_sem_comprar', 'perfil',
            'created_at', 'updated_at'
        ]

    # ── Campos derivados dos PEDIDOS, não dos contadores ──────────────────
    #
    # `total_spent`, `total_orders` e `last_order_at` são gravados por signal.
    # Em 07/ago, 12 dos 78 clientes da Cê Saladas estavam errados: a lista
    # somava R$ 2.726,01 e os pedidos somavam R$ 2.613,21. Contador
    # denormalizado que ninguém reconcilia sempre diverge — pedido editado,
    # cancelado depois de pago, restauração de backup.
    #
    # Os campos antigos ficam (há consumidor que os lê); estes é que a tela usa.

    gasto_real = serializers.SerializerMethodField()
    pedidos_reais = serializers.SerializerMethodField()
    dias_sem_comprar = serializers.SerializerMethodField()
    perfil = serializers.SerializerMethodField()

    def get_gasto_real(self, obj):
        return float(getattr(obj, '_gasto_real', 0) or 0)

    def get_pedidos_reais(self, obj):
        return int(getattr(obj, '_pedidos_reais', 0) or 0)

    def get_dias_sem_comprar(self, obj):
        """Dias desde a última compra que conta como receita.

        `None` — e não 0 — para quem nunca comprou: zero lê como "comprou
        hoje", mentira perigosa numa lista ordenada por reengajamento.
        """
        ultima = getattr(obj, '_ultima_compra', None)
        if not ultima:
            return None
        from apps.stores.metrics import hoje_local
        return (hoje_local() - ultima.astimezone().date()).days

    def get_perfil(self, obj):
        """Classificação por número de pedidos, com régua explícita.

        novo 0–1 · ocasional 2–4 · vip 5+. Sem régua, "VIP" é rótulo mágico
        que ninguém consegue explicar nem contestar.
        """
        n = int(getattr(obj, '_pedidos_reais', 0) or 0)
        if n >= 5:
            return 'vip'
        if n >= 2:
            return 'ocasional'
        return 'novo'

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email

    def get_default_address(self, obj):
        return obj.get_default_address()

    def _sync_address_list(self, customer, addresses):
        """Replace-all por id: atualiza os com id, cria os sem id, apaga os ausentes."""
        existing = {str(a.id): a for a in customer.address_list.all()}
        incoming_ids = set()
        for addr in addresses:
            addr_id = addr.get('id')
            if addr_id and str(addr_id) in existing:
                obj = existing[str(addr_id)]
                for field, value in addr.items():
                    if field == 'id':
                        continue
                    setattr(obj, field, value)
                obj.save()
                incoming_ids.add(str(addr_id))
            else:
                payload = {k: v for k, v in addr.items() if k != 'id'}
                StoreCustomerAddress.objects.create(customer=customer, **payload)
        # apaga os que sumiram do payload
        for old_id, obj in existing.items():
            if old_id not in incoming_ids:
                obj.delete()

    def create(self, validated_data):
        address_list = validated_data.pop('address_list', None)
        name = validated_data.pop('name', '')
        store = validated_data.get('store')
        phone = validated_data.get('phone', '') or validated_data.get('whatsapp', '')
        with transaction.atomic():
            # Reusa CustomerIdentityService para criar User interno com padrão
            # consistente (username único, email @pastita.local) — CLAUDE.md
            user, _profile, _created = CustomerIdentityService.resolve_user(
                phone=phone or '',
                full_name=name or '',
                create=True,
            )
            validated_data['user'] = user
            # M-4: unique_together(store, user) — get_or_create evita IntegrityError
            # (500) quando o mesmo cliente é enviado duas vezes pelo dashboard.
            customer, _created = StoreCustomer.objects.get_or_create(
                store=store,
                user=user,
                defaults=validated_data,
            )
            if address_list is not None:
                self._sync_address_list(customer, address_list)
            return customer

    def update(self, instance, validated_data):
        address_list = validated_data.pop('address_list', None)
        name = validated_data.pop('name', None)
        with transaction.atomic():
            if name is not None:
                first, last = CustomerIdentityService.split_name(name)
                instance.user.first_name = first
                instance.user.last_name = last
                instance.user.save(update_fields=['first_name', 'last_name'])
                # A identidade CANÔNICA é UnifiedUser.name — é o que a comanda, o
                # CRM e a criação de pedido leem. Sem atualizá-la, editar o nome
                # gravava só no auth.User e ficava invisível ("Desconhecido Nasche"
                # continuava aparecendo). Espelha o nome cheio aqui.
                full = f"{first} {last}".strip() or (name or '').strip()
                uu = getattr(instance, 'unified_user', None)
                if uu is not None:
                    uu.name = full
                    uu.save(update_fields=['name'])
                # O pedido guarda o nome como SNAPSHOT (customer_name) do momento
                # da criação. Corrigir o cliente não reescreve pedidos passados —
                # daí a comanda continuava "Desconhecido". Propaga o nome novo só
                # para os pedidos DESTE cliente cujo snapshot ainda é placeholder
                # (nunca sobrescreve um nome real digitado no pedido).
                if full and instance.user_id:
                    from apps.stores.models import StoreOrder
                    from django.db.models import Q
                    StoreOrder.objects.filter(customer=instance.user).filter(
                        Q(customer_name__icontains='desconhecido')
                        | Q(customer_name='')
                        | Q(customer_name__istartswith='cliente_')
                    ).update(customer_name=full)
            instance = super().update(instance, validated_data)
            if address_list is not None:
                self._sync_address_list(instance, address_list)
            return instance


class StoreStatsSerializer(serializers.Serializer):
    """Serializer for store statistics."""
    
    orders = serializers.DictField()
    revenue = serializers.DictField()
    products = serializers.DictField()
    customers = serializers.DictField()
    daily_orders = serializers.ListField()


# =============================================================================
# CART SERIALIZERS
# =============================================================================

from apps.stores.models import StoreCart, StoreCartItem, StoreCartComboItem, StoreCombo, StoreProductType


class StoreCartItemSerializer(serializers.ModelSerializer):
    """Serializer for cart items."""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    variant_name = serializers.CharField(source='variant.name', read_only=True, allow_null=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = StoreCartItem
        fields = [
            'id', 'product', 'product_name', 'product_image',
            'variant', 'variant_name',
            'quantity', 'unit_price', 'subtotal',
            'options', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_product_image(self, obj):
        return obj.product.get_main_image_url()


class StoreCartComboItemSerializer(serializers.ModelSerializer):
    """Serializer for cart combo items with group selections."""

    combo_name = serializers.SerializerMethodField()
    combo_image = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    selected_variants_data = serializers.SerializerMethodField()

    class Meta:
        model = StoreCartComboItem
        fields = [
            'id', 'combo', 'combo_name', 'combo_image',
            'quantity', 'unit_price', 'subtotal',
            'group_selections', 'selected_variants_data', 'customizations', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_combo_name(self, obj):
        return obj.effective_name

    def get_combo_image(self, obj):
        return obj.combo.get_image_url() if obj.combo else None

    def get_unit_price(self, obj):
        return str(obj.effective_price)

    def get_selected_variants_data(self, obj):
        if not obj.combo_id:
            return []
        from apps.stores.services.checkout_service import CheckoutService
        # Resolve o snapshot de TODOS os combos do carrinho de uma vez (nº
        # constante de queries) e cacheia — este método roda por item.
        cache = getattr(self, '_selection_snapshot_cache', None)
        if cache is None or obj.id not in cache:
            siblings = [ci for ci in obj.cart.combo_items.all() if ci.combo_id] if obj.cart_id else []
            if obj.id not in {ci.id for ci in siblings}:
                siblings.append(obj)
            cache = CheckoutService.build_combo_selection_snapshots(siblings)
            self._selection_snapshot_cache = cache
        return cache[obj.id]['selected_variants_data']


class StoreCartSerializer(serializers.ModelSerializer):
    """Serializer for shopping cart."""
    
    items = StoreCartItemSerializer(many=True, read_only=True)
    combo_items = StoreCartComboItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    
    class Meta:
        model = StoreCart
        fields = [
            'id', 'store', 'store_name', 'user',
            'items', 'combo_items',
            'subtotal', 'item_count', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class AddToCartSerializer(serializers.Serializer):
    """Serializer for adding items to cart."""
    
    product_id = serializers.UUIDField(required=False)
    combo_id = serializers.UUIDField(required=False)
    variant_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    options = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    
    def validate(self, data):
        if not data.get('product_id') and not data.get('combo_id'):
            raise serializers.ValidationError("product_id ou combo_id é obrigatório")
        return data


class UpdateCartItemSerializer(serializers.Serializer):
    """Serializer for updating cart item quantity."""
    
    quantity = serializers.IntegerField(min_value=0)


# =============================================================================
# CHECKOUT SERIALIZERS
# =============================================================================

class CheckoutSerializer(serializers.Serializer):
    """Serializer for checkout process."""

    # Customer info
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(max_length=20)
    
    # Delivery info
    delivery_method = serializers.ChoiceField(choices=['delivery', 'pickup'], default='delivery')
    delivery_address = serializers.DictField(required=False)
    delivery_notes = serializers.CharField(required=False, allow_blank=True, default='')
    distance_km = serializers.DecimalField(max_digits=7, decimal_places=2, required=False, allow_null=True)
    
    # Payment
    payment_method = serializers.ChoiceField(choices=['pix', 'card', 'cash'], default='pix')
    
    # Coupon
    coupon_code = serializers.CharField(required=False, allow_blank=True, default='')
    
    # Notes
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class CheckoutResponseSerializer(serializers.Serializer):
    """Serializer for checkout response."""
    
    success = serializers.BooleanField()
    order_id = serializers.UUIDField(required=False)
    order_number = serializers.CharField(required=False)
    
    # Payment info
    payment_id = serializers.CharField(required=False)
    payment_status = serializers.CharField(required=False)
    
    # PIX data
    pix_code = serializers.CharField(required=False)
    pix_qr_code = serializers.CharField(required=False)
    pix_expiration = serializers.DateTimeField(required=False)
    
    # Redirect URL (for card payments)
    redirect_url = serializers.URLField(required=False)
    
    # Totals
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    
    # Error
    error = serializers.CharField(required=False)


# =============================================================================
# CATALOG SERIALIZERS
# =============================================================================

class CatalogProductTypeSerializer(serializers.ModelSerializer):
    """Lightweight product type serializer for public catalog (no store/products_count)."""

    class Meta:
        model = StoreProductType
        fields = [
            'id', 'name', 'slug', 'description',
            'icon', 'image', 'custom_fields',
            'sort_order', 'is_active', 'show_in_menu',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


def build_combo_groups(obj):
    """Monta os grupos de um combo com opções (variantes E/OU produtos).

    Compartilhado entre StoreComboSerializer (admin) e PublicComboSerializer
    (storefront) para garantir paridade do contrato de exibição.
    """
    groups_data = []
    for group in sorted(obj.groups.all(), key=lambda g: g.position):
        anchor_price = group.product.price if group.product_id else 0
        variants = []
        for limit in group.variant_limits.all():
            variant = limit.variant
            v_prod = getattr(variant, 'product', None)
            v_tracks = bool(getattr(v_prod, 'track_stock', False)) and not bool(getattr(v_prod, 'allow_backorder', False))
            variants.append({
                'variant_id': str(variant.id),
                'name': variant.name,
                'variant_name': variant.name,
                'price': float(variant.price or anchor_price),
                'price_override': float(limit.price_override) if limit.price_override else None,
                # stock=None (ilimitado) quando não rastreia estoque/permite backorder;
                # senão o modal desabilita a opção achando que está esgotada.
                'stock': (variant.stock_quantity if v_tracks else None),
                'max_selections': limit.max_selections,
                'image_url': variant.image.url if variant.image else variant.image_url,
            })

        # Opções de PRODUTO (escolha entre vários produtos no grupo)
        product_options = []
        for opt in sorted(group.product_options.all(), key=lambda o: o.position):
            p = opt.product
            p_img = (p.main_image.url if getattr(p, 'main_image', None) else None) or getattr(p, 'main_image_url', None)
            p_tracks = bool(getattr(p, 'track_stock', False)) and not bool(getattr(p, 'allow_backorder', False))
            product_options.append({
                'product_id': str(p.id),
                'name': p.name,
                'price': float(opt.price_override) if opt.price_override is not None else float(p.price),
                'price_override': float(opt.price_override) if opt.price_override is not None else None,
                # stock=None (ilimitado) p/ produto sob encomenda (track_stock=False) —
                # senão o modal trata como esgotado e desabilita a opção do combo.
                'stock': (p.stock_quantity if p_tracks else None),
                'max_selections': opt.max_selections,
                'image_url': p_img,
            })

        groups_data.append({
            'id': str(group.id),
            'product_id': str(group.product.id) if group.product_id else None,
            'product_name': group.product.name if group.product_id else (group.title or ''),
            'title': group.title or (group.product.name if group.product_id else ''),
            'is_required': group.is_required,
            'min_selections': group.min_selections,
            'max_selections': group.max_selections,
            'allow_duplicate_variants': group.allow_duplicate_variants,
            'position': group.position,
            'variant_limits': variants,
            'product_options': product_options,
        })

    return groups_data


class StoreComboSerializer(serializers.ModelSerializer):
    """Serializer for combos with product groups."""

    groups = serializers.JSONField(required=False)
    # image_url é o URLField gravável do model (não method field): permite que o
    # dash salve a imagem do combo por URL. A saída final é normalizada em
    # to_representation via get_image_url() do model.
    savings = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    savings_percentage = serializers.IntegerField(read_only=True)
    catalog_role = serializers.SerializerMethodField()
    merchandising_flags = serializers.SerializerMethodField()

    class Meta:
        model = StoreCombo
        fields = [
            'id', 'store', 'name', 'slug', 'description',
            'price', 'compare_at_price', 'savings', 'savings_percentage',
            'image', 'image_url',
            'is_active', 'featured',
            'track_stock', 'stock_quantity', 'dynamic_pricing',
            # `metadata` guarda loyalty_units e `inclui` (o brinde fixo que o
            # agente de WhatsApp lê). Sem ele nos fields, o painel não tinha
            # como cadastrar e o dado só entrava por shell.
            'metadata',
            'groups', 'catalog_role', 'merchandising_flags',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        return obj.get_image_url()

    def get_catalog_role(self, obj):
        return 'bundle'

    def get_merchandising_flags(self, obj):
        return {
            'is_featured': bool(obj.featured),
            'is_upsell': False,
            'is_cross_sell': True,
            'category_slug': 'combos',
            'product_type_slug': 'combo',
        }

    def get_groups(self, obj):
        """Retorna grupos com opções (variantes E/OU produtos) para seleção."""
        return build_combo_groups(obj)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['image_url'] = instance.get_image_url()
        data['groups'] = self.get_groups(instance)
        return data

    def _sync_groups(self, combo, groups_data):
        from apps.stores.models.combo_group import (
            ComboProductGroup,
            ComboProductGroupVariantLimit,
            ComboProductGroupProductOption,
        )

        combo.groups.all().delete()
        for idx, group_data in enumerate(groups_data or []):
            product_id = group_data.get('product') or group_data.get('product_id')
            product_options = group_data.get('product_options') or []
            # Grupo de VARIANTES tem produto-âncora; grupo de PRODUTOS tem
            # product_options (sem âncora). Pula só o grupo totalmente vazio.
            if not product_id and not product_options:
                continue
            group = ComboProductGroup.objects.create(
                combo=combo,
                product_id=product_id or None,
                title=group_data.get('title') or '',
                is_required=group_data.get('is_required', True),
                min_selections=group_data.get('min_selections', 1),
                max_selections=group_data.get('max_selections', 1),
                allow_duplicate_variants=group_data.get('allow_duplicate_variants', False),
                position=group_data.get('position', idx),
            )
            for limit_data in group_data.get('variant_limits') or []:
                variant_id = limit_data.get('variant') or limit_data.get('variant_id')
                if not variant_id:
                    continue
                ComboProductGroupVariantLimit.objects.create(
                    group=group,
                    variant_id=variant_id,
                    max_selections=limit_data.get('max_selections') or 1,
                    price_override=limit_data.get('price_override') or None,
                )
            for pos, opt_data in enumerate(product_options):
                opt_product_id = opt_data.get('product') or opt_data.get('product_id')
                if not opt_product_id:
                    continue
                ComboProductGroupProductOption.objects.create(
                    group=group,
                    product_id=opt_product_id,
                    max_selections=opt_data.get('max_selections') or 1,
                    price_override=opt_data.get('price_override') or None,
                    position=opt_data.get('position', pos),
                )

    @transaction.atomic
    def create(self, validated_data):
        groups_data = validated_data.pop('groups', None)
        combo = super().create(validated_data)
        if groups_data is not None:
            self._sync_groups(combo, groups_data)
        return combo

    @transaction.atomic
    def update(self, instance, validated_data):
        groups_data = validated_data.pop('groups', None)
        combo = super().update(instance, validated_data)
        if groups_data is not None:
            self._sync_groups(combo, groups_data)
        return combo



class StoreCatalogSerializer(serializers.Serializer):
    """Serializer for store catalog."""

    store = StoreSerializer()
    categories = StoreCategorySerializer(many=True)
    product_types = CatalogProductTypeSerializer(many=True)
    products = StoreProductSerializer(many=True)
    combos = StoreComboSerializer(many=True)
    featured_products = StoreProductSerializer(many=True)


# =============================================================================
# COUPON SERIALIZERS
# =============================================================================

from apps.stores.models import StoreCoupon, StoreDeliveryZone, StoreOrderComboItem, StoreBioLink


class StoreCouponSerializer(serializers.ModelSerializer):
    """Serializer for store coupons."""
    
    discount_type_display = serializers.CharField(source='get_discount_type_display', read_only=True)
    is_valid_now = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCoupon
        fields = [
            'id', 'store', 'code', 'description',
            'discount_type', 'discount_type_display', 'discount_value',
            'min_purchase', 'max_discount',
            'usage_limit', 'usage_limit_per_user', 'used_count',
            'is_active', 'valid_from', 'valid_until',
            'first_order_only', 'is_featured',
            'applicable_categories', 'applicable_products',
            'is_valid_now',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'used_count', 'created_at', 'updated_at']
    
    def get_is_valid_now(self, obj):
        valid, _ = obj.is_valid()
        return valid


class StoreSlugOrIdField(serializers.Field):
    """Field that accepts either store UUID or slug."""
    
    def to_representation(self, value):
        return str(value.id) if value else None
    
    def to_internal_value(self, data):
        import uuid as uuid_module
        from apps.stores.models import Store
        from apps.core.permissions import user_can_access_store

        if not data:
            return None

        store = None
        try:
            uuid_module.UUID(str(data))
            store = Store.objects.filter(id=data).first()
        except (ValueError, AttributeError):
            pass

        if not store:
            store = Store.objects.filter(slug=data).first()

        if not store:
            raise serializers.ValidationError(f"Loja não encontrada: {data}")

        # Tenant gate: bloqueia acesso cross-tenant para usuários comuns.
        # is_staff não bypassa — apenas is_superuser tem acesso irrestrito.
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            if not user_can_access_store(request.user, store):
                raise serializers.ValidationError('Loja não encontrada')

        return store


class StoreCouponCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating coupons."""
    
    store = StoreSlugOrIdField(required=False, allow_null=True)
    
    class Meta:
        model = StoreCoupon
        fields = [
            'store', 'code', 'description',
            'discount_type', 'discount_value',
            'min_purchase', 'max_discount',
            'usage_limit', 'usage_limit_per_user',
            'is_active', 'valid_from', 'valid_until',
            'first_order_only', 'is_featured',
            'applicable_categories', 'applicable_products'
        ]


class CouponValidateSerializer(serializers.Serializer):
    """Serializer for coupon validation request."""
    
    code = serializers.CharField(max_length=50)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)


class CouponValidateResponseSerializer(serializers.Serializer):
    """Serializer for coupon validation response."""
    
    valid = serializers.BooleanField()
    coupon_id = serializers.UUIDField(required=False)
    code = serializers.CharField(required=False)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount_type = serializers.CharField(required=False)
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    error = serializers.CharField(required=False)


# =============================================================================
# DELIVERY ZONE SERIALIZERS
# =============================================================================

class StoreDeliveryZoneSerializer(serializers.ModelSerializer):
    """Serializer for delivery zones."""
    
    zone_type_display = serializers.CharField(source='get_zone_type_display', read_only=True)
    distance_band_display = serializers.SerializerMethodField()
    distance_label = serializers.SerializerMethodField()  # Alias for frontend compatibility
    store_name = serializers.CharField(source='store.name', read_only=True)
    
    class Meta:
        model = StoreDeliveryZone
        fields = [
            'id', 'store', 'store_name', 'name',
            'zone_type', 'zone_type_display',
            'distance_band', 'distance_band_display', 'distance_label',
            'min_km', 'max_km',
            'zip_code_start', 'zip_code_end',
            'min_minutes', 'max_minutes',
            'polygon_coordinates',
            'delivery_fee', 'min_fee', 'fee_per_km',
            'estimated_minutes', 'estimated_days',
            'color', 'is_active', 'sort_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_distance_band_display(self, obj):
        if obj.distance_band:
            return dict(StoreDeliveryZone.DISTANCE_BAND_CHOICES).get(obj.distance_band, obj.distance_band)
        return None
    
    def get_distance_label(self, obj):
        """Alias for distance_band_display for frontend compatibility."""
        return self.get_distance_band_display(obj)


class StoreDeliveryZoneCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating delivery zones."""

    class Meta:
        model = StoreDeliveryZone
        fields = [
            'store', 'name', 'zone_type',
            'distance_band', 'min_km', 'max_km',
            'zip_code_start', 'zip_code_end',
            'min_minutes', 'max_minutes',
            'polygon_coordinates',
            'delivery_fee', 'min_fee', 'fee_per_km',
            'estimated_minutes', 'estimated_days',
            'color', 'is_active', 'sort_order'
        ]

    def validate_store(self, value):
        """Bloqueia acesso cross-tenant: apenas superuser pode usar qualquer loja."""
        from apps.core.permissions import user_can_access_store
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            if not user_can_access_store(request.user, value):
                raise serializers.ValidationError('Loja não encontrada')
        return value


class DeliveryFeeRequestSerializer(serializers.Serializer):
    """Serializer for delivery fee calculation request."""
    
    distance_km = serializers.DecimalField(max_digits=7, decimal_places=2, required=False)
    zip_code = serializers.CharField(max_length=10, required=False)
    lat = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    lng = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)


class DeliveryFeeResponseSerializer(serializers.Serializer):
    """Serializer for delivery fee calculation response."""
    
    fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    zone_id = serializers.UUIDField(required=False)
    zone_name = serializers.CharField(required=False)
    estimated_minutes = serializers.IntegerField(required=False)
    available = serializers.BooleanField(default=True)
    error = serializers.CharField(required=False)


# =============================================================================
# ORDER COMBO ITEM SERIALIZER
# =============================================================================

class StoreOrderComboItemSerializer(serializers.ModelSerializer):
    """Serializer for order combo items with group selections."""

    combo_name = serializers.SerializerMethodField()
    combo_price = serializers.SerializerMethodField()

    class Meta:
        model = StoreOrderComboItem
        fields = [
            'id', 'combo', 'combo_name', 'combo_price',
            'order_item', 'quantity', 'group_selections',
            'selected_variant_ids', 'selected_variants_data',
            'display_data',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_combo_name(self, obj):
        if obj.combo:
            return obj.combo.name
        return obj.display_data.get('combo_name', 'Combo')

    def get_combo_price(self, obj):
        if obj.combo:
            return str(obj.combo.price)
        if obj.order_item:
            return str(obj.order_item.unit_price)
        return ''


# Update StoreOrderSerializer to include combo_items
class StoreOrderFullSerializer(serializers.ModelSerializer):
    """Full serializer for StoreOrder including combo items."""
    
    items = StoreOrderItemSerializer(many=True, read_only=True)
    combo_items = StoreOrderComboItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    delivery_method_display = serializers.CharField(source='get_delivery_method_display', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    store_slug = serializers.CharField(source='store.slug', read_only=True)
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreOrder
        fields = [
            'id', 'store', 'store_name', 'store_slug', 'order_number', 'access_token',
            'customer', 'customer_name', 'customer_email', 'customer_phone',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'subtotal', 'discount', 'coupon_code', 'tax', 'delivery_fee', 'total',
            'payment_method', 'payment_id', 'payment_preference_id',
            'pix_code', 'pix_qr_code', 'pix_ticket_url',
            'delivery_method', 'delivery_method_display',
            'delivery_address', 'delivery_notes',
            'scheduled_date', 'scheduled_time',
            'tracking_code', 'tracking_url', 'carrier',
            'customer_notes', 'internal_notes',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at',
            'items', 'combo_items', 'items_count', 'metadata',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'order_number', 'access_token', 'created_at', 'updated_at',
            'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at'
        ]
    
    def get_items_count(self, obj):
        return len(obj.items.all())


# =============================================================================
# PUBLIC CATALOG SERIALIZERS (for storefront)
# =============================================================================

class PublicProductSerializer(serializers.ModelSerializer):
    """Public product serializer for storefront (no sensitive data)."""
    
    main_image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    is_paused = serializers.ReadOnlyField()
    
    class Meta:
        model = StoreProduct
        fields = [
            'id', 'name', 'slug', 'description', 'short_description',
            'price', 'compare_at_price',
            'is_on_sale', 'discount_percentage',
            'stock_quantity', 'is_in_stock', 'is_paused',
            'status', 'featured',
            'main_image_url', 'images',
            'category', 'category_name', 'category_slug',
            'attributes', 'tags'
        ]
    
    def get_main_image_url(self, obj):
        return obj.get_main_image_url()


class PublicComboSerializer(serializers.ModelSerializer):
    """Public combo serializer for storefront."""

    groups = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    savings = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    savings_percentage = serializers.IntegerField(read_only=True)
    is_in_stock = serializers.SerializerMethodField()
    
    class Meta:
        model = StoreCombo
        fields = [
            'id', 'name', 'slug', 'description',
            'price', 'compare_at_price', 'savings', 'savings_percentage',
            'image_url',
            'is_active', 'featured',
            'stock_quantity', 'is_in_stock', 'dynamic_pricing',
            'groups'
        ]
    
    def get_image_url(self, obj):
        return obj.get_image_url()

    def get_groups(self, obj):
        """Mesmo contrato de grupos do StoreComboSerializer (variantes/produtos)."""
        return build_combo_groups(obj)

    def get_is_in_stock(self, obj):
        if not obj.track_stock:
            return True
        return obj.stock_quantity > 0


class PublicCatalogSerializer(serializers.Serializer):
    """Public catalog serializer for storefront."""

    store = serializers.SerializerMethodField()
    categories = StoreCategorySerializer(many=True)
    product_types = CatalogProductTypeSerializer(many=True)
    products = PublicProductSerializer(many=True)
    products_by_category = serializers.DictField()
    combos = PublicComboSerializer(many=True)
    combos_destaque = PublicComboSerializer(many=True)
    featured_products = PublicProductSerializer(many=True)

    def get_store(self, obj):
        store = obj.get('store')
        if store:
            # Prova social: nota média + contagem de avaliações públicas
            from django.db.models import Avg, Count
            agg = store.reviews.filter(is_public=True).aggregate(
                avg=Avg('rating'), n=Count('id'),
            )
            avg_rating = round(agg['avg'], 1) if agg['avg'] is not None else None
            return {
                'id': str(store.id),
                'name': store.name,
                'slug': store.slug,
                'description': store.description,
                'logo_url': store.get_logo_url(),
                'primary_color': store.primary_color,
                'secondary_color': store.secondary_color,
                'phone': store.phone,
                'whatsapp_number': store.whatsapp_number,
                'address': store.address,
                'city': store.city,
                'state': store.state,
                'latitude': str(store.latitude) if store.latitude else None,
                'longitude': str(store.longitude) if store.longitude else None,
                'delivery_enabled': store.delivery_enabled,
                'pickup_enabled': store.pickup_enabled,
                'min_order_value': str(store.min_order_value),
                'default_delivery_fee': str(store.default_delivery_fee),
                'free_delivery_threshold': (
                    str(store.free_delivery_threshold) if store.free_delivery_threshold else None
                ),
                'avg_rating': avg_rating,
                'reviews_count': agg['n'],
                'is_open': store.is_open(),
            }
        return None


# =============================================================================
# BIO LINK SERIALIZERS (Link na Bio)
# =============================================================================


class BioLinkSerializer(serializers.ModelSerializer):
    """Serializer for a store's custom bio-page links."""

    store = StoreSlugOrIdField()

    class Meta:
        model = StoreBioLink
        fields = ['id', 'store', 'title', 'url', 'icon', 'icon_url', 'sort_order', 'is_active']
        read_only_fields = ['id']
