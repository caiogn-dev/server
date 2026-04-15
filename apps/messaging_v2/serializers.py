"""
Serializers completos para messaging_v2.
"""
from rest_framework import serializers
from .models import PlatformAccount, Conversation, UnifiedMessage, MessageTemplate


class PlatformAccountSerializer(serializers.ModelSerializer):
    """Serializer para contas de plataforma unificadas."""
    
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = PlatformAccount
        fields = [
            'id', 'platform', 'platform_display', 'name',
            'phone_number', 'phone_number_id', 'waba_id',
            'display_phone_number', 'page_id', 'page_name',
            'instagram_account_id', 'access_token',
            'status', 'status_display', 'is_active', 'is_verified',
            'webhook_verified', 'auto_response_enabled',
            'human_handoff_enabled', 'category', 'followers_count',
            'last_sync_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'is_verified', 'webhook_verified',
            'last_sync_at', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'access_token': {'write_only': True}
        }
    
    def validate(self, data):
        """Validar campos específicos por plataforma."""
        platform = data.get('platform')
        
        if platform == PlatformAccount.Platform.WHATSAPP:
            if not data.get('phone_number_id'):
                raise serializers.ValidationError({
                    'phone_number_id': 'Obrigatório para WhatsApp'
                })
            if not data.get('waba_id'):
                raise serializers.ValidationError({
                    'waba_id': 'Obrigatório para WhatsApp'
                })
        
        elif platform == PlatformAccount.Platform.MESSENGER:
            if not data.get('page_id'):
                raise serializers.ValidationError({
                    'page_id': 'Obrigatório para Messenger'
                })
        
        elif platform == PlatformAccount.Platform.INSTAGRAM:
            if not data.get('instagram_account_id'):
                raise serializers.ValidationError({
                    'instagram_account_id': 'Obrigatório para Instagram'
                })
        
        return data
    
    def create(self, validated_data):
        """Criar conta associada ao usuário atual."""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer para conversas."""
    
    platform_account_name = serializers.CharField(
        source='platform_account.name', read_only=True
    )
    platform_display = serializers.CharField(
        source='get_platform_display', read_only=True
    )
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'platform_account', 'platform_account_name',
            'customer_id', 'customer_name', 'customer_phone',
            'customer_profile_pic', 'platform', 'platform_display',
            'is_open', 'unread_count', 'last_message_at',
            'last_message', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'unread_count', 'last_message_at',
            'created_at', 'updated_at'
        ]
    
    def get_last_message(self, obj):
        """Retornar última mensagem da conversa."""
        last_msg = obj.messages.first()
        if last_msg:
            return {
                'id': str(last_msg.id),
                'text': last_msg.text[:100] if last_msg.text else '',
                'message_type': last_msg.message_type,
                'direction': last_msg.direction,
                'status': last_msg.status,
                'created_at': last_msg.created_at.isoformat()
            }
        return None


class UnifiedMessageSerializer(serializers.ModelSerializer):
    """Serializer para mensagens."""
    
    conversation_id = serializers.UUIDField(source='conversation.id', read_only=True)
    customer_name = serializers.CharField(
        source='conversation.customer_name', read_only=True
    )
    customer_phone = serializers.CharField(
        source='conversation.customer_phone', read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = UnifiedMessage
        fields = [
            'id', 'conversation', 'conversation_id',
            'customer_name', 'customer_phone',
            'direction', 'status', 'status_display',
            'message_type', 'text', 'media_url', 'media_caption',
            'external_id', 'template_name', 'template_params',
            'sent_at', 'delivered_at', 'read_at',
            'metadata', 'created_at'
        ]
        read_only_fields = [
            'id', 'status', 'external_id',
            'sent_at', 'delivered_at', 'read_at', 'created_at'
        ]


class MessageTemplateSerializer(serializers.ModelSerializer):
    """Serializer para templates de mensagem."""
    
    platform_account_name = serializers.CharField(
        source='platform_account.name', read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = MessageTemplate
        fields = [
            'id', 'platform_account', 'platform_account_name',
            'name', 'language', 'category', 'category_display',
            'status', 'status_display', 'header', 'body',
            'footer', 'buttons', 'external_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'external_id', 'created_at', 'updated_at'
        ]
