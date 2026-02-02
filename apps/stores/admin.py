from django.contrib import admin
from .models import (
    Store, StoreIntegration, StoreWebhook, StoreCategory,
    StoreProduct, StoreProductVariant, StoreOrder, StoreOrderItem,
    StoreCustomer,
    StorePaymentGateway, StorePayment, StorePaymentWebhookEvent,
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'store_type', 'status', 'owner', 'created_at']
    list_filter = ['store_type', 'status', 'created_at']
    search_fields = ['name', 'slug', 'email']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreIntegration)
class StoreIntegrationAdmin(admin.ModelAdmin):
    list_display = ['store', 'integration_type', 'name', 'status', 'created_at']
    list_filter = ['integration_type', 'status']
    search_fields = ['store__name', 'name']


@admin.register(StoreWebhook)
class StoreWebhookAdmin(admin.ModelAdmin):
    list_display = ['store', 'name', 'url', 'is_active', 'total_calls', 'successful_calls']
    list_filter = ['is_active', 'store']
    search_fields = ['store__name', 'name', 'url']


@admin.register(StoreCategory)
class StoreCategoryAdmin(admin.ModelAdmin):
    list_display = ['store', 'name', 'slug', 'parent', 'is_active', 'sort_order']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'store__name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreProduct)
class StoreProductAdmin(admin.ModelAdmin):
    list_display = ['store', 'name', 'sku', 'price', 'stock_quantity', 'status']
    list_filter = ['store', 'status', 'category']
    search_fields = ['name', 'sku', 'store__name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreProductVariant)
class StoreProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'name', 'sku', 'price', 'stock_quantity', 'is_active']
    list_filter = ['is_active', 'product__store']
    search_fields = ['name', 'sku', 'product__name']


@admin.register(StoreOrder)
class StoreOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'store', 'customer_name', 'status', 'payment_status', 'total', 'created_at']
    list_filter = ['store', 'status', 'payment_status', 'delivery_method']
    search_fields = ['order_number', 'customer_name', 'customer_email', 'customer_phone']
    readonly_fields = ['order_number']


@admin.register(StoreOrderItem)
class StoreOrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product_name', 'quantity', 'unit_price', 'subtotal']
    list_filter = ['order__store']
    search_fields = ['product_name', 'order__order_number']


@admin.register(StoreCustomer)
class StoreCustomerAdmin(admin.ModelAdmin):
    list_display = ['store', 'user', 'phone', 'total_orders', 'total_spent', 'created_at']
    list_filter = ['store', 'accepts_marketing']
    search_fields = ['user__email', 'phone', 'whatsapp']


@admin.register(StorePaymentGateway)
class StorePaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'gateway_type', 'is_enabled', 'is_default', 'is_sandbox', 'created_at']
    list_filter = ['gateway_type', 'is_enabled', 'is_default', 'is_sandbox', 'store']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(StorePayment)
class StorePaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_id', 'order', 'gateway', 'status', 'amount', 'currency', 'created_at']
    list_filter = ['status', 'payment_method', 'gateway__gateway_type', 'created_at']
    search_fields = ['payment_id', 'external_id', 'order__order_number', 'payer_email', 'payer_name']
    readonly_fields = ['payment_id', 'created_at', 'updated_at', 'paid_at']
    date_hierarchy = 'created_at'


@admin.register(StorePaymentWebhookEvent)
class StorePaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'gateway', 'processing_status', 'created_at']
    list_filter = ['processing_status', 'event_type', 'gateway__gateway_type', 'created_at']
    search_fields = ['event_id', 'event_type']
    readonly_fields = ['event_id', 'payload', 'headers', 'created_at', 'processed_at']
    date_hierarchy = 'created_at'
