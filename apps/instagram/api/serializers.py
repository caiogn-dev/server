"""
Instagram API Serializers.
"""
from rest_framework import serializers
from apps.instagram.models import (
    InstagramAccount,
    InstagramConversation,
    InstagramMessage,
    InstagramWebhookEvent
)


class InstagramAccountSerializer(serializers.ModelSerializer):
    """Serializer for Instagram accounts."""
    
    masked_token = serializers.ReadOnlyField()
    
    class Meta:
        model = InstagramAccount
        fields = [
            'id',
            'name',
            'instagram_account_id',
            'instagram_user_id',
            'facebook_page_id',
            'username',
            'app_id',
            'status',
            'messaging_enabled',
            'auto_response_enabled',
            'human_handoff_enabled',
            'profile_picture_url',
            'followers_count',
            'masked_token',
            'token_expires_at',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 
            'instagram_account_id',
            'instagram_user_id',
            'status',
            'masked_token',
            'token_expires_at',
            'profile_picture_url',
            'followers_count',
            'created_at', 
            'updated_at'
        ]


class InstagramAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Instagram accounts."""
    
    access_token = serializers.CharField(write_only=True)
    app_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    facebook_page_id = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = InstagramAccount
        fields = [
            'name',
            'instagram_account_id',
            'instagram_user_id',
            'facebook_page_id',
            'username',
            'app_id',
            'app_secret',
            'access_token',
            'webhook_verify_token',
            'messaging_enabled',
            'auto_response_enabled'
        ]
    
    def create(self, validated_data):
        access_token = validated_data.pop('access_token')
        app_secret = validated_data.pop('app_secret', '')
        
        account = InstagramAccount(**validated_data)
        account.access_token = access_token
        account.app_secret = app_secret or ''
        account.status = InstagramAccount.AccountStatus.ACTIVE
        account.save()
        
        return account


class InstagramConversationSerializer(serializers.ModelSerializer):
    """Serializer for Instagram conversations."""
    
    unread_count = serializers.SerializerMethodField()
    
    class Meta:
        model = InstagramConversation
        fields = [
            'id',
            'participant_id',
            'participant_username',
            'participant_name',
            'participant_profile_pic',
            'status',
            'message_count',
            'unread_count',
            'last_message_at',
            'last_message_preview',
            'assigned_to',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'participant_id',
            'participant_username',
            'participant_name',
            'participant_profile_pic',
            'message_count',
            'last_message_at',
            'last_message_preview',
            'created_at',
            'updated_at'
        ]
    
    def get_unread_count(self, obj):
        return InstagramMessage.objects.filter(
            conversation=obj,
            direction=InstagramMessage.MessageDirection.INBOUND,
            status__in=[
                InstagramMessage.MessageStatus.DELIVERED,
                InstagramMessage.MessageStatus.PENDING
            ]
        ).count()


class InstagramMessageSerializer(serializers.ModelSerializer):
    """Serializer for Instagram messages."""
    
    class Meta:
        model = InstagramMessage
        fields = [
            'id',
            'instagram_message_id',
            'conversation',
            'direction',
            'message_type',
            'status',
            'sender_id',
            'recipient_id',
            'text_content',
            'media_url',
            'media_type',
            'shared_media_id',
            'shared_media_url',
            'reply_to_message_id',
            'sent_at',
            'delivered_at',
            'seen_at',
            'error_code',
            'error_message',
            'created_at'
        ]
        read_only_fields = [
            'id',
            'instagram_message_id',
            'direction',
            'message_type',
            'status',
            'sender_id',
            'recipient_id',
            'sent_at',
            'delivered_at',
            'seen_at',
            'error_code',
            'error_message',
            'created_at'
        ]


class SendMessageSerializer(serializers.Serializer):
    """Serializer for sending messages."""
    
    recipient_id = serializers.CharField(required=True)
    text = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.URLField(required=False, allow_blank=True)
    video_url = serializers.URLField(required=False, allow_blank=True)
    quick_replies = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True
    )
    
    def validate(self, data):
        if not data.get('text') and not data.get('image_url') and not data.get('video_url'):
            raise serializers.ValidationError("At least one of text, image_url, or video_url is required")
        return data


class InstagramWebhookEventSerializer(serializers.ModelSerializer):
    """Serializer for webhook events (for debugging)."""
    
    class Meta:
        model = InstagramWebhookEvent
        fields = [
            'id',
            'event_id',
            'event_type',
            'processing_status',
            'payload',
            'processed_at',
            'retry_count',
            'error_message',
            'created_at'
        ]
        read_only_fields = fields
