"""
Messaging API Serializers - LEGACY.

DEPRECATED: Use messaging_v2 para a versão unificada.
"""
from rest_framework import serializers
from ..models import PlatformAccount, UnifiedConversation, UnifiedMessage


class PlatformAccountSerializer(serializers.ModelSerializer):
    """Serializer LEGACY para PlatformAccount."""
    class Meta:
        model = PlatformAccount
        fields = [
            'id', 'platform', 'name', 'phone_number',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UnifiedConversationSerializer(serializers.ModelSerializer):
    """Serializer LEGACY para UnifiedConversation."""
    class Meta:
        model = UnifiedConversation
        fields = [
            'id', 'platform_account', 'customer_name',
            'is_open', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UnifiedMessageSerializer(serializers.ModelSerializer):
    """Serializer LEGACY para UnifiedMessage."""
    class Meta:
        model = UnifiedMessage
        fields = [
            'id', 'conversation', 'direction',
            'text', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# Aliases para compatibilidade
MessengerAccountSerializer = PlatformAccountSerializer
MessengerConversationSerializer = UnifiedConversationSerializer
MessengerMessageSerializer = UnifiedMessageSerializer
