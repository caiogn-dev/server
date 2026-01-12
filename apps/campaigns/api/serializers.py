"""
Campaign API serializers.
"""
from rest_framework import serializers
from ..models import Campaign, CampaignRecipient, ScheduledMessage, ContactList


class CampaignRecipientSerializer(serializers.ModelSerializer):
    """Serializer for CampaignRecipient model."""
    
    class Meta:
        model = CampaignRecipient
        fields = [
            'id', 'phone_number', 'contact_name', 'status',
            'sent_at', 'delivered_at', 'read_at', 'failed_at',
            'error_code', 'error_message', 'variables',
        ]
        read_only_fields = ['id']


class CampaignSerializer(serializers.ModelSerializer):
    """Serializer for Campaign model."""
    delivery_rate = serializers.FloatField(read_only=True)
    read_rate = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Campaign
        fields = [
            'id', 'account', 'name', 'description', 'campaign_type', 'status',
            'template', 'message_content', 'audience_type', 'audience_filters',
            'scheduled_at', 'started_at', 'completed_at',
            'messages_per_minute', 'delay_between_messages',
            'total_recipients', 'messages_sent', 'messages_delivered',
            'messages_read', 'messages_failed', 'delivery_rate', 'read_rate',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'started_at', 'completed_at',
            'total_recipients', 'messages_sent', 'messages_delivered',
            'messages_read', 'messages_failed', 'created_at', 'updated_at',
        ]


class CampaignCreateSerializer(serializers.Serializer):
    """Serializer for creating campaigns."""
    account_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    campaign_type = serializers.ChoiceField(
        choices=Campaign.CampaignType.choices,
        default=Campaign.CampaignType.BROADCAST
    )
    template_id = serializers.UUIDField(required=False, allow_null=True)
    message_content = serializers.DictField(required=False, default=dict)
    audience_filters = serializers.DictField(required=False, default=dict)
    contact_list = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)


class AddRecipientsSerializer(serializers.Serializer):
    """Serializer for adding recipients."""
    contacts = serializers.ListField(
        child=serializers.DictField(),
        min_length=1
    )


class ScheduledMessageSerializer(serializers.ModelSerializer):
    """Serializer for ScheduledMessage model."""
    
    class Meta:
        model = ScheduledMessage
        fields = [
            'id', 'account', 'to_number', 'contact_name',
            'message_type', 'content', 'template', 'template_variables',
            'scheduled_at', 'timezone', 'status',
            'message_id', 'whatsapp_message_id', 'sent_at',
            'error_code', 'error_message',
            'is_recurring', 'recurrence_rule', 'next_occurrence',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'message_id', 'whatsapp_message_id',
            'sent_at', 'error_code', 'error_message',
            'next_occurrence', 'created_at', 'updated_at',
        ]


class ScheduledMessageCreateSerializer(serializers.Serializer):
    """Serializer for creating scheduled messages."""
    account_id = serializers.UUIDField()
    to_number = serializers.CharField(max_length=20)
    contact_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    message_type = serializers.CharField(max_length=20, default='text')
    content = serializers.DictField(required=False, default=dict)
    template_id = serializers.UUIDField(required=False, allow_null=True)
    template_variables = serializers.DictField(required=False, default=dict)
    scheduled_at = serializers.DateTimeField()
    timezone = serializers.CharField(max_length=50, default='UTC')
    is_recurring = serializers.BooleanField(default=False)
    recurrence_rule = serializers.CharField(max_length=255, required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)


class ContactListSerializer(serializers.ModelSerializer):
    """Serializer for ContactList model."""
    
    class Meta:
        model = ContactList
        fields = [
            'id', 'account', 'name', 'description',
            'contacts', 'contact_count', 'source', 'imported_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'contact_count', 'imported_at', 'created_at', 'updated_at']


class ContactListCreateSerializer(serializers.Serializer):
    """Serializer for creating contact lists."""
    account_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    contacts = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )


class ImportContactsSerializer(serializers.Serializer):
    """Serializer for importing contacts from CSV."""
    account_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    csv_content = serializers.CharField()
