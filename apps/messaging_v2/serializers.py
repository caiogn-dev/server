"""
Serializers completos para messaging_v2.
"""
from rest_framework import serializers
from .models import PlatformAccount, Conversation, UnifiedMessage, MessageTemplate


class PlatformAccountSerializer(serializers.ModelSerializer):
    """Serializer para contas de plataforma."""
    
    class Meta:
        model = PlatformAccount
        fields = [
            'id', 'platform', 'name', 'phone_number',
            'is_active', 'is_verified', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer para conversas."""
    store_name = serializers.CharField(source='store.name', read_only=True)
    unread_count = serializers.IntegerField(read_only=True, default=0)
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'store', 'store_name', 'customer_phone', 'customer_name',
            'platform', 'is_open', 'last_message_at', 'unread_count',
            'last_message', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_last_message(self, obj):
        """Retornar última mensagem da conversa."""
        last_msg = obj.messages.first()
        if last_msg:
            return {
                'id': str(last_msg.id),
                'text': last_msg.text[:100],
                'direction': last_msg.direction,
                'status': last_msg.status,
                'created_at': last_msg.created_at.isoformat()
            }
        return None


class UnifiedMessageSerializer(serializers.ModelSerializer):
    """Serializer para mensagens."""
    conversation_id = serializers.UUIDField(source='conversation.id', read_only=True)
    customer_phone = serializers.CharField(source='conversation.customer_phone', read_only=True)
    
    class Meta:
        model = UnifiedMessage
        fields = [
            'id', 'conversation', 'conversation_id', 'customer_phone',
            'direction', 'status', 'text', 'media_url', 'external_id',
            'sent_at', 'delivered_at', 'read_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class MessageTemplateSerializer(serializers.ModelSerializer):
    """Serializer para templates de mensagem."""
    
    class Meta:
        model = MessageTemplate
        fields = [
            'id', 'name', 'category', 'language', 'header',
            'body', 'footer', 'buttons', 'status', 'external_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
