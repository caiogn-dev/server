from django.contrib import admin
from .models import Store, Category, Product, Customer, Order, Payment


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'phone', 'email', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'slug', 'phone']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'created_at']
    list_filter = ['store']
    search_fields = ['name', 'description']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'price', 'stock_quantity', 'category']
    list_filter = ['store', 'category']
    search_fields = ['name', 'description', 'sku']
    list_editable = ['price', 'stock_quantity']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'store']
    list_filter = ['store']
    search_fields = ['name', 'phone', 'email']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'store', 'total', 'status', 'payment_status', 'created_at']
    list_filter = ['status', 'payment_status', 'store', 'created_at']
    search_fields = ['id', 'customer_name', 'customer_phone']
    date_hierarchy = 'created_at'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['order', 'amount', 'status', 'payment_method', 'provider_payment_id', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['provider_payment_id', 'order__id']
