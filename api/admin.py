from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Product, Cart, CartItem, Order, OrderItem, Checkout, PaymentNotification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'phone', 'created_at']
    list_filter = ['created_at', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'cpf', 'phone']
    ordering = ['-created_at']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Info', {
            'fields': ('phone', 'cpf', 'date_of_birth', 'profile_image',
                      'address', 'city', 'state', 'zip_code', 'country')
        }),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'price', 'stock_quantity', 'category', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['name', 'sku', 'description']
    ordering = ['-created_at']
    fieldsets = (
        ('Product Info', {
            'fields': ('name', 'description', 'price', 'sku', 'category')
        }),
        ('Stock & Media', {
            'fields': ('stock_quantity', 'image')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'updated_at']
    list_filter = ['created_at']
    search_fields = ['user__email', 'user__username']
    ordering = ['-created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'created_at']
    list_filter = ['created_at']
    search_fields = ['cart__user__email', 'product__name']
    ordering = ['-created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['order_number', 'user__email', 'user__username']
    ordering = ['-created_at']
    fieldsets = (
        ('Order Info', {
            'fields': ('order_number', 'user', 'total_amount', 'status', 'notes')
        }),
        ('Shipping Address', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_state',
                      'shipping_zip_code', 'shipping_country')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['id', 'order_number', 'created_at', 'updated_at']


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'price', 'created_at']
    list_filter = ['created_at', 'order']
    search_fields = ['order__order_number', 'product__name']
    ordering = ['-created_at']
    readonly_fields = ['id', 'created_at']


@admin.register(Checkout)
class CheckoutAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'user', 'total_amount', 'payment_status', 'payment_method', 'created_at']
    list_filter = ['payment_status', 'payment_method', 'created_at']
    search_fields = ['order__order_number', 'user__email', 'customer_email', 'session_token']
    ordering = ['-created_at']
    fieldsets = (
        ('Checkout Info', {
            'fields': ('order', 'user', 'total_amount', 'session_token')
        }),
        ('Payment Info', {
            'fields': ('payment_status', 'payment_method', 'mercado_pago_payment_id',
                      'mercado_pago_preference_id', 'payment_link')
        }),
        ('Customer Info', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('Billing Address', {
            'fields': ('billing_address', 'billing_city', 'billing_state',
                      'billing_zip_code', 'billing_country')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'expires_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['id', 'session_token', 'created_at', 'updated_at']


@admin.register(PaymentNotification)
class PaymentNotificationAdmin(admin.ModelAdmin):
    list_display = ['notification_type', 'mercado_pago_id', 'status', 'processed', 'created_at']
    list_filter = ['notification_type', 'status', 'processed', 'created_at']
    search_fields = ['mercado_pago_id', 'checkout__id']
    ordering = ['-created_at']
    fieldsets = (
        ('Notification Info', {
            'fields': ('notification_type', 'mercado_pago_id', 'status', 'status_detail')
        }),
        ('Processing', {
            'fields': ('checkout', 'processed', 'error_message')
        }),
        ('Payload', {
            'fields': ('payload',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['id', 'created_at', 'processed_at']
