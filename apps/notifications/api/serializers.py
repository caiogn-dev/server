"""
Notification API serializers.
"""
from rest_framework import serializers
from ..models import Notification, NotificationPreference, PushSubscription


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'priority', 'title', 'message',
            'data', 'related_object_type', 'related_object_id',
            'is_read', 'read_at', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for NotificationPreference model."""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'email_enabled', 'email_messages', 'email_orders',
            'email_payments', 'email_system',
            'push_enabled', 'push_messages', 'push_orders',
            'push_payments', 'push_system',
            'inapp_enabled', 'inapp_sound',
        ]


class PushSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for PushSubscription model."""
    
    class Meta:
        model = PushSubscription
        fields = ['id', 'endpoint', 'p256dh_key', 'auth_key', 'user_agent', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class RegisterPushSubscriptionSerializer(serializers.Serializer):
    """Serializer for registering push subscription."""
    endpoint = serializers.CharField()
    p256dh_key = serializers.CharField()
    auth_key = serializers.CharField()
    user_agent = serializers.CharField(required=False, allow_blank=True)


class MarkReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read."""
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False
    )
    mark_all = serializers.BooleanField(default=False)
