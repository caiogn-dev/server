"""
Order admin configuration.
"""
from django.contrib import admin
from .models import Order, OrderItem, OrderEvent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['total_price']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 'account', 'customer_phone', 'customer_name',
        'status', 'total', 'created_at'
    ]
    list_filter = ['status', 'account', 'created_at']
    search_fields = ['order_number', 'customer_phone', 'customer_name', 'customer_email']
    readonly_fields = [
        'id', 'order_number', 'subtotal', 'total', 'confirmed_at',
        'paid_at', 'shipped_at', 'delivered_at', 'cancelled_at',
        'created_at', 'updated_at'
    ]
    raw_id_fields = ['account', 'conversation']
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Order Info', {
            'fields': ('order_number', 'account', 'conversation', 'status')
        }),
        ('Customer', {
            'fields': ('customer_phone', 'customer_name', 'customer_email')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'discount', 'shipping_cost', 'tax', 'total', 'currency')
        }),
        ('Addresses', {
            'fields': ('shipping_address', 'billing_address'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes', 'internal_notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'confirmed_at', 'paid_at', 'shipped_at',
                'delivered_at', 'cancelled_at', 'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ['order', 'event_type', 'actor', 'created_at']
    list_filter = ['event_type', 'created_at']
    search_fields = ['order__order_number', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['order', 'actor']
