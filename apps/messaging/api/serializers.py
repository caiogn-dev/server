from rest_framework import serializers
from ..models import (
    MessengerAccount, MessengerProfile, MessengerConversation,
    MessengerMessage, MessengerBroadcast, MessengerSponsoredMessage,
    MessengerExtension, MessengerWebhookLog
)


class MessengerAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerAccount
        fields = [
            'id', 'page_id', 'page_name', 'category',
            'followers_count', 'is_active', 'webhook_verified',
            'created_at', 'updated_at', 'last_sync_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessengerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerProfile
        fields = [
            'greeting_text', 'get_started_payload',
            'persistent_menu', 'ice_breakers',
            'whitelisted_domains', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class MessengerMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerMessage
        fields = [
            'id', 'messenger_message_id', 'message_type',
            'content', 'attachment_url', 'attachment_type',
            'template_payload', 'quick_replies',
            'is_from_page', 'is_read', 'delivered_at', 'read_at',
            'sent_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class MessengerConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = MessengerConversation
        fields = [
            'id', 'messenger_conversation_id', 'psid',
            'participant_name', 'participant_profile_pic',
            'is_active', 'unread_count', 'last_message_at',
            'last_message', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'type': last_msg.message_type,
                'content': last_msg.content[:100] if last_msg.content else None,
                'created_at': last_msg.created_at.isoformat()
            }
        return None


class MessengerBroadcastSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerBroadcast
        fields = [
            'id', 'name', 'message_type', 'content',
            'template_payload', 'target_audience',
            'status', 'total_recipients', 'sent_count',
            'delivered_count', 'read_count',
            'scheduled_at', 'started_at', 'completed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessengerSponsoredMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerSponsoredMessage
        fields = [
            'id', 'name', 'ad_account_id', 'message_type',
            'content', 'template_payload', 'targeting',
            'daily_budget', 'total_budget', 'status',
            'impressions', 'clicks', 'spent',
            'facebook_ad_id', 'start_time', 'end_time',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessengerExtensionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerExtension
        fields = [
            'id', 'name', 'extension_type', 'url',
            'icon_url', 'webview_height_ratio',
            'in_test', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessengerWebhookLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessengerWebhookLog
        fields = [
            'id', 'object_type', 'payload',
            'is_processed', 'processed_at', 'error_message',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']