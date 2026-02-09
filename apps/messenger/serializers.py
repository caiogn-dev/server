"""
Messenger API Serializers
"""
from rest_framework import serializers
from .models import (
    MessengerAccount,
    MessengerConversation,
    MessengerMessage,
    MessengerBroadcast,
    MessengerSponsoredMessage
)


class MessengerAccountSerializer(serializers.ModelSerializer):
    """Serializer for Messenger accounts."""
    
    class Meta:
        model = MessengerAccount
        fields = [
            'id', 'name', 'page_id', 'page_name', 'status',
            'webhook_verified', 'auto_response_enabled', 'human_handoff_enabled',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessengerAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Messenger accounts."""
    page_access_token = serializers.CharField(write_only=True)
    
    class Meta:
        model = MessengerAccount
        fields = [
            'name', 'page_id', 'page_name', 'page_access_token'
        ]


class MessengerConversationSerializer(serializers.ModelSerializer):
    """Serializer for Messenger conversations."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = MessengerConversation
        fields = [
            'id', 'account', 'account_name', 'sender_id', 'sender_name',
            'status', 'last_message', 'last_message_at', 'unread_count',
            'is_bot_active', 'handover_status', 'assigned_to',
            'created_at', 'updated_at'
        ]


class MessengerMessageSerializer(serializers.ModelSerializer):
    """Serializer for Messenger messages."""
    
    class Meta:
        model = MessengerMessage
        fields = [
            'id', 'conversation', 'sender_id', 'sender_name',
            'content', 'message_type', 'media_url', 'attachments',
            'is_from_bot', 'is_read', 'mid', 'created_at'
        ]


class MessengerBroadcastSerializer(serializers.ModelSerializer):
    """Serializer for Messenger broadcasts."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = MessengerBroadcast
        fields = [
            'id', 'account', 'account_name', 'name', 'content',
            'message_type', 'status', 'scheduled_at', 'sent_at',
            'recipient_count', 'sent_count', 'delivered_count', 'failed_count',
            'created_at'
        ]
        read_only_fields = [
            'sent_count', 'delivered_count', 'failed_count', 'created_at'
        ]


class MessengerSponsoredSerializer(serializers.ModelSerializer):
    """Serializer for sponsored messages."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = MessengerSponsoredMessage
        fields = [
            'id', 'account', 'account_name', 'name', 'content',
            'image_url', 'cta_type', 'cta_url',
            'budget', 'currency', 'status', 'created_at'
        ]
