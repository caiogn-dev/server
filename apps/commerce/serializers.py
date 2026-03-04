"""
Commerce - Serializers.
"""
from rest_framework import serializers
from .models import Store, Category, Product, Customer, Order, Payment


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ['id', 'name', 'slug', 'description', 'phone', 'email', 'is_active', 'created_at']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent', 'is_active']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'price', 'stock_quantity', 'sku', 'category', 'category_name', 'images', 'is_active']


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'name', 'phone', 'email', 'whatsapp_id', 'total_orders', 'total_spent']


class OrderItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    
    class Meta:
        model = Order
        fields = ['id', 'customer', 'status', 'subtotal', 'total', 'items', 'created_at']
        read_only_fields = ['subtotal', 'total']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'order', 'provider', 'status', 'amount', 'payment_method', 'created_at']
