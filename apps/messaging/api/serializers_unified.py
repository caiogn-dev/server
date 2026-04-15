"""
Serializers for unified messaging models.
"""

from rest_framework import serializers
from apps.messaging.models import (
    PlatformAccount,
    UnifiedConversation,
    UnifiedMessage,
    UnifiedTemplate,
)


class PlatformAccountSerializer(serializers.ModelSerializer):
    """Serializer for PlatformAccount."""
    
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    masked_token = serializers.CharField(read_only=True)
    
    # Platform-specific fields
    waba_id = serializers.CharField(read_only=True)
    phone_number_id = serializers.CharField(read_only=True)
    page_id = serializers.CharField(read_only=True)
    
    class Meta:
        model = PlatformAccount
        fields = [
            'id',
            'platform',
            'platform_display',
            'name',
            'external_id',
            'parent_id',
            'phone_number',
            'display_phone_number',
            'status',
            'status_display',
            'is_active',
            'is_verified',
            'webhook_verified',
            'masked_token',
            'auto_response_enabled',
            'human_handoff_enabled',
            'metadata',
            'last_sync_at',
            'created_at',
            'updated_at',
            # Platform-specific
            'waba_id',
            'phone_number_id',
            'page_id',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'last_sync_at',
            'platform_display',
            'status_display',
            'masked_token',
        ]


class PlatformAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating PlatformAccount."""
    
    access_token = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = PlatformAccount
        fields = [
            'platform',
            'name',
            'external_id',
            'parent_id',
            'phone_number',
            'display_phone_number',
            'access_token',
            'webhook_verify_token',
            'auto_response_enabled',
            'human_handoff_enabled',
            'metadata',
        ]
    
    def create(self, validated_data):
        access_token = validated_data.pop('access_token', None)
        account = super().create(validated_data)
        if access_token:
            account.access_token = access_token
            account.save()
        return account


class PlatformAccountUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating PlatformAccount."""
    
    access_token = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = PlatformAccount
        fields = [
            'name',
            'phone_number',
            'display_phone_number',
            'access_token',
            'webhook_verify_token',
            'is_active',
            'auto_response_enabled',
            'human_handoff_enabled',
            'metadata',
        ]
    
    def update(self, instance, validated_data):
        access_token = validated_data.pop('access_token', None)
        instance = super().update(instance, validated_data)
        if access_token:
            instance.access_token = access_token
            instance.save()
        return instance


class UnifiedConversationSerializer(serializers.ModelSerializer):
    """Serializer for UnifiedConversation."""
    
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = UnifiedConversation
        fields = [
            'id',
            'platform',
            'platform_display',
            'external_id',
            'customer_phone',
            'customer_name',
            'customer_email',
            'customer_profile_pic',
            'customer_platform_id',
            'status',
            'status_display',
            'is_active',
            'unread_count',
            'assigned_to',
            'assigned_at',
            'ai_enabled',
            'last_message_at',
            'last_message_preview',
            'last_message',
            'source',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'platform_display',
            'status_display',
        ]
    
    def get_last_message(self, obj):
        """Get last message for conversation."""
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'id': str(last_msg.id),
                'type': last_msg.message_type,
                'text': last_msg.text_body[:100] if last_msg.text_body else None,
                'direction': last_msg.direction,
                'status': last_msg.status,
                'created_at': last_msg.created_at.isoformat(),
            }
        return None


class UnifiedMessageSerializer(serializers.ModelSerializer):
    """Serializer for UnifiedMessage."""
    
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    direction_display = serializers.CharField(source='get_direction_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    message_type_display = serializers.CharField(source='get_message_type_display', read_only=True)
    preview = serializers.CharField(source='preview', read_only=True)
    
    class Meta:
        model = UnifiedMessage
        fields = [
            'id',
            'conversation',
            'platform',
            'platform_display',
            'direction',
            'direction_display',
            'message_type',
            'message_type_display',
            'text_body',
            'content',
            'media_url',
            'media_mime_type',
            'media_caption',
            'template_name',
            'external_id',
            'context_message_id',
            'is_forwarded',
            'status',
            'status_display',
            'sent_at',
            'delivered_at',
            'read_at',
            'error_code',
            'error_message',
            'processed_by_agent',
            'source',
            'preview',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'platform_display',
            'direction_display',
            'status_display',
            'message_type_display',
            'preview',
        ]


class UnifiedMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating UnifiedMessage."""
    
    class Meta:
        model = UnifiedMessage
        fields = [
            'conversation',
            'text_body',
            'content',
            'media_url',
            'media_caption',
            'template_name',
            'message_type',
        ]


class UnifiedTemplateSerializer(serializers.ModelSerializer):
    """Serializer for UnifiedTemplate."""
    
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)
    
    class Meta:
        model = UnifiedTemplate
        fields = [
            'id',
            'name',
            'platform',
            'platform_display',
            'template_type',
            'template_type_display',
            'external_id',
            'language',
            'category',
            'category_display',
            'status',
            'status_display',
            'header',
            'body',
            'footer',
            'buttons',
            'components',
            'variables',
            'sample_values',
            'rejection_reason',
            'version',
            'is_active',
            'submitted_at',
            'approved_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'platform_display',
            'status_display',
            'category_display',
            'template_type_display',
        ]


class UnifiedTemplateCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating UnifiedTemplate."""
    
    class Meta:
        model = UnifiedTemplate
        fields = [
            'platform_account',
            'name',
            'platform',
            'template_type',
            'language',
            'category',
            'header',
            'body',
            'footer',
            'buttons',
            'components',
            'variables',
            'sample_values',
        ]
