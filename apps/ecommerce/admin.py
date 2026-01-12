"""
Legacy E-commerce admin configuration.
These models are kept for migration compatibility only.
Use apps.stores admin for active management.
"""
from django.contrib import admin
from .models import Product, Cart, Checkout, Coupon, DeliveryZone


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'price', 'is_active', 'created_at']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'sku']
    ordering = ['-created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'created_at']
    list_filter = ['created_at']


@admin.register(Checkout)
class CheckoutAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_name', 'payment_status', 'total_amount', 'created_at']
    list_filter = ['payment_status', 'created_at']


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_type', 'discount_value', 'is_active']
    list_filter = ['is_active', 'discount_type']


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'zone_type', 'delivery_fee', 'is_active']
    list_filter = ['is_active', 'zone_type']
