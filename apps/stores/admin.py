from django.contrib import admin
# from unfold.admin import ModelAdmin as UnfoldModelAdmin, TabularInline
# Using standard Django admin instead (unfold v1.2.4 is broken)
UnfoldModelAdmin = admin.ModelAdmin
TabularInline = admin.TabularInline

from .models import (
    Store, StoreIntegration, StoreWebhook, StoreCategory,
    StoreProduct, StoreProductVariant, StoreOrder, StoreOrderItem,
    StoreCustomer, StoreTeamMember,
    StorePaymentGateway, StorePayment, StorePaymentWebhookEvent,
    StoreCombo,
)
from .models.combo_group import (
    ComboProductGroup,
    ComboProductGroupVariantLimit,
    ComboProductGroupProductOption,
)


class StoreTeamMemberInline(TabularInline):
    model = StoreTeamMember
    extra = 0
    fields = ('user', 'role', 'is_active', 'invited_by')
    readonly_fields = ('invited_by',)
    fk_name = 'tenant'


@admin.register(Store)
class StoreAdmin(UnfoldModelAdmin):
    list_display = ['name', 'slug', 'store_type', 'status', 'custom_domain', 'owner', 'created_at']
    list_filter = ['store_type', 'status', 'template', 'created_at']
    search_fields = ['name', 'slug', 'email', 'custom_domain']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    inlines = [StoreTeamMemberInline]
    fieldsets = (
        ('Informacoes Basicas', {
            'fields': ('owner', 'name', 'slug', 'description', 'store_type', 'status'),
        }),
        ('Branding', {
            'fields': ('logo', 'logo_url', 'banner', 'banner_url', 'primary_color', 'secondary_color'),
        }),
        ('Storefront', {
            'fields': ('template', 'tagline', 'custom_domain'),
            'description': 'Configuracoes do cardapio publico multi-tenant',
        }),
        ('Contato', {
            'fields': ('email', 'phone', 'whatsapp_number', 'website_url', 'menu_url', 'order_url'),
        }),
        ('Endereco', {
            'fields': ('address', 'city', 'state', 'zip_code', 'country', 'latitude', 'longitude'),
        }),
        ('Delivery', {
            'fields': ('delivery_enabled', 'pickup_enabled', 'min_order_value', 'free_delivery_threshold', 'default_delivery_fee'),
        }),
        ('Config', {
            'fields': ('currency', 'timezone', 'tax_rate', 'operating_hours', 'metadata'),
            'classes': ('collapse',),
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(StoreTeamMember)
class StoreTeamMemberAdmin(UnfoldModelAdmin):
    list_display = ('user', 'tenant', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('user__email', 'user__username', 'tenant__name')
    fk_name = 'tenant'
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StoreIntegration)
class StoreIntegrationAdmin(UnfoldModelAdmin):
    list_display = ['store', 'integration_type', 'name', 'status', 'created_at']
    list_filter = ['integration_type', 'status']
    search_fields = ['store__name', 'name']


@admin.register(StoreWebhook)
class StoreWebhookAdmin(UnfoldModelAdmin):
    list_display = ['store', 'name', 'url', 'is_active', 'total_calls', 'successful_calls']
    list_filter = ['is_active', 'store']
    search_fields = ['store__name', 'name', 'url']


@admin.register(StoreCategory)
class StoreCategoryAdmin(UnfoldModelAdmin):
    list_display = ['store', 'name', 'slug', 'parent', 'is_active', 'sort_order']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'store__name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreProduct)
class StoreProductAdmin(UnfoldModelAdmin):
    list_display = ['store', 'name', 'sku', 'price', 'stock_quantity', 'status']
    list_filter = ['store', 'status', 'category']
    search_fields = ['name', 'sku', 'store__name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreProductVariant)
class StoreProductVariantAdmin(UnfoldModelAdmin):
    list_display = ['product', 'name', 'sku', 'price', 'stock_quantity', 'is_active']
    list_filter = ['is_active', 'product__store']
    search_fields = ['name', 'sku', 'product__name']


@admin.register(StoreOrder)
class StoreOrderAdmin(UnfoldModelAdmin):
    list_display = ['order_number', 'store', 'customer_name', 'status', 'payment_status', 'total', 'created_at']
    list_filter = ['store', 'status', 'payment_status', 'delivery_method']
    search_fields = ['order_number', 'customer_name', 'customer_email', 'customer_phone']
    readonly_fields = ['order_number']


@admin.register(StoreOrderItem)
class StoreOrderItemAdmin(UnfoldModelAdmin):
    list_display = ['order', 'product_name', 'quantity', 'unit_price', 'subtotal']
    list_filter = ['order__store']
    search_fields = ['product_name', 'order__order_number']


@admin.register(StoreCustomer)
class StoreCustomerAdmin(UnfoldModelAdmin):
    list_display = ['store', 'user', 'phone', 'total_orders', 'total_spent', 'created_at']
    list_filter = ['store', 'accepts_marketing']
    search_fields = ['user__email', 'phone', 'whatsapp']


@admin.register(StorePaymentGateway)
class StorePaymentGatewayAdmin(UnfoldModelAdmin):
    list_display = ['name', 'store', 'gateway_type', 'is_enabled', 'is_default', 'is_sandbox', 'created_at']
    list_filter = ['gateway_type', 'is_enabled', 'is_default', 'is_sandbox', 'store']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(StorePayment)
class StorePaymentAdmin(UnfoldModelAdmin):
    list_display = ['payment_id', 'order', 'gateway', 'status', 'amount', 'currency', 'created_at']
    list_filter = ['status', 'payment_method', 'gateway__gateway_type', 'created_at']
    search_fields = ['payment_id', 'external_id', 'order__order_number', 'payer_email', 'payer_name']
    readonly_fields = ['payment_id', 'created_at', 'updated_at', 'paid_at']
    date_hierarchy = 'created_at'


@admin.register(StorePaymentWebhookEvent)
class StorePaymentWebhookEventAdmin(UnfoldModelAdmin):
    list_display = ['event_type', 'gateway', 'processing_status', 'created_at']
    list_filter = ['processing_status', 'event_type', 'gateway__gateway_type', 'created_at']
    search_fields = ['event_id', 'event_type']
    readonly_fields = ['event_id', 'payload', 'headers', 'created_at', 'processed_at']
    date_hierarchy = 'created_at'


# ── Combos ───────────────────────────────────────────────────────────────────

class ComboProductGroupInline(TabularInline):
    model = ComboProductGroup
    extra = 0
    fields = ('title', 'product', 'is_required', 'min_selections', 'max_selections', 'position')
    show_change_link = True


@admin.register(StoreCombo)
class StoreComboAdmin(UnfoldModelAdmin):
    list_display = ['name', 'store', 'price', 'compare_at_price', 'is_active', 'featured', 'created_at']
    list_filter = ['store', 'is_active', 'featured']
    search_fields = ['name', 'slug', 'store__name']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ComboProductGroupInline]


class ComboProductGroupVariantLimitInline(TabularInline):
    model = ComboProductGroupVariantLimit
    extra = 0
    fields = ('variant', 'max_selections', 'price_override')


class ComboProductGroupProductOptionInline(TabularInline):
    model = ComboProductGroupProductOption
    extra = 0
    fields = ('product', 'max_selections', 'price_override', 'position')


@admin.register(ComboProductGroup)
class ComboProductGroupAdmin(UnfoldModelAdmin):
    list_display = ['__str__', 'combo', 'product', 'title', 'min_selections', 'max_selections', 'position']
    list_filter = ['combo__store', 'is_required']
    search_fields = ['title', 'combo__name', 'product__name']
    inlines = [ComboProductGroupVariantLimitInline, ComboProductGroupProductOptionInline]
