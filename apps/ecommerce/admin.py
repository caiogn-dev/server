"""
E-commerce admin configuration.
"""
from django.contrib import admin
from .models import Product, Cart, CartItem, Checkout


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'price', 'stock_quantity', 'category', 'is_active', 'created_at']
    list_filter = ['is_active', 'category', 'created_at']
    search_fields = ['name', 'sku', 'description']
    ordering = ['-created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['id', 'created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'phone_number', 'get_item_count', 'get_total', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email', 'phone_number', 'session_key']
    inlines = [CartItemInline]
    readonly_fields = ['id', 'created_at', 'updated_at']

    def get_item_count(self, obj):
        return obj.get_item_count()
    get_item_count.short_description = 'Items'

    def get_total(self, obj):
        return f"R$ {obj.get_total():.2f}"
    get_total.short_description = 'Total'


@admin.register(Checkout)
class CheckoutAdmin(admin.ModelAdmin):
    list_display = [
        'session_token_short', 'customer_name', 'customer_phone',
        'total_amount', 'payment_status', 'created_at'
    ]
    list_filter = ['payment_status', 'created_at']
    search_fields = ['session_token', 'customer_name', 'customer_email', 'customer_phone']
    readonly_fields = [
        'id', 'session_token', 'mercado_pago_preference_id',
        'mercado_pago_payment_id', 'created_at', 'updated_at', 'completed_at'
    ]
    fieldsets = (
        ('Checkout Info', {
            'fields': ('id', 'session_token', 'cart', 'order', 'user')
        }),
        ('Payment', {
            'fields': (
                'total_amount', 'payment_status', 'payment_link',
                'pix_code', 'pix_qr_code',
                'mercado_pago_preference_id', 'mercado_pago_payment_id'
            )
        }),
        ('Customer', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('Shipping', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_state', 'shipping_zip_code')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'expires_at', 'completed_at')
        }),
    )

    def session_token_short(self, obj):
        return f"{obj.session_token[:8]}..."
    session_token_short.short_description = 'Token'
