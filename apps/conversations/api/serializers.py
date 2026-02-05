"""
Conversation API serializers.
"""
from rest_framework import serializers
from ..models import Conversation, ConversationNote


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for Conversation."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    assigned_agent_name = serializers.CharField(
        source='assigned_agent.username',
        read_only=True,
        allow_null=True
    )
    ai_agent_name = serializers.CharField(
        source='ai_agent.name',
        read_only=True,
        allow_null=True
    )
    message_count = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'account', 'account_name', 'phone_number', 'contact_name',
            'mode', 'status', 'assigned_agent', 'assigned_agent_name',
            'ai_agent', 'ai_agent_name', 'agent_session_id', 'context', 'tags',
            'last_message_at', 'last_message_preview', 'unread_count',
            'last_customer_message_at', 'last_agent_message_at',
            'closed_at', 'resolved_at', 'message_count',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'last_message_at', 'last_customer_message_at',
            'last_agent_message_at', 'closed_at', 'resolved_at',
            'created_at', 'updated_at'
        ]

    def get_message_count(self, obj):
        return obj.messages.count() if hasattr(obj, 'messages') else 0

    def get_last_message_preview(self, obj):
        """Get preview of the last message in the conversation."""
        if hasattr(obj, 'messages'):
            last_msg = obj.messages.order_by('-created_at').first()
            if last_msg:
                text = last_msg.text_body or ''
                return text[:50] + '...' if len(text) > 50 else text
        return ''

    def get_unread_count(self, obj):
        """Count unread inbound messages."""
        if hasattr(obj, 'messages'):
            return obj.messages.filter(
                direction='inbound',
                read_at__isnull=True
            ).count()
        return 0


class ConversationNoteSerializer(serializers.ModelSerializer):
    """Serializer for Conversation Note."""
    author_name = serializers.CharField(source='author.username', read_only=True, allow_null=True)
    
    class Meta:
        model = ConversationNote
        fields = [
            'id', 'conversation', 'author', 'author_name', 'content',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SwitchModeSerializer(serializers.Serializer):
    """Serializer for switching conversation mode."""
    agent_id = serializers.IntegerField(required=False, allow_null=True)


class AddNoteSerializer(serializers.Serializer):
    """Serializer for adding a note."""
    content = serializers.CharField(max_length=5000)


class UpdateContextSerializer(serializers.Serializer):
    """Serializer for updating context."""
    context = serializers.DictField()


class TagSerializer(serializers.Serializer):
    """Serializer for tag operations."""
    tag = serializers.CharField(max_length=50)


class AssignAgentSerializer(serializers.Serializer):
    """Serializer for assigning agent."""
    agent_id = serializers.IntegerField()
