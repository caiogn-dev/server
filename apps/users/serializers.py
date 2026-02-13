"""
Serializers para UnifiedUser API.
"""
from rest_framework import serializers
from .models import UnifiedUser, UnifiedUserActivity


class UnifiedUserSerializer(serializers.ModelSerializer):
    """Serializer para UnifiedUser."""
    
    context_for_agent = serializers.CharField(
        source='get_context_for_agent',
        read_only=True
    )
    
    class Meta:
        model = UnifiedUser
        fields = [
            'id', 'email', 'phone_number', 'google_id',
            'name', 'profile_picture',
            'total_orders', 'total_spent', 'last_order_at',
            'has_abandoned_cart', 'abandoned_cart_value',
            'abandoned_cart_items', 'abandoned_cart_since',
            'first_seen_at', 'last_seen_at', 'is_active',
            'context_for_agent',
        ]
        read_only_fields = [
            'id', 'first_seen_at', 'last_seen_at',
            'total_orders', 'total_spent',
        ]


class UnifiedUserListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listagem."""
    
    class Meta:
        model = UnifiedUser
        fields = [
            'id', 'name', 'phone_number', 'email',
            'total_orders', 'has_abandoned_cart',
            'last_seen_at',
        ]


class UnifiedUserActivitySerializer(serializers.ModelSerializer):
    """Serializer para atividades."""
    
    class Meta:
        model = UnifiedUserActivity
        fields = [
            'id', 'activity_type', 'description',
            'metadata', 'created_at',
        ]
