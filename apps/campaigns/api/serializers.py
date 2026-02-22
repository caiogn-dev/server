"""
Campaign API serializers - Unified with Automation.

Note: ScheduledMessage serializers have been moved to apps.automation.api.serializers.
"""
from rest_framework import serializers
from ..models import Campaign, CampaignRecipient, ContactList


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
            'messages_per_minute', 'delay_between_seconds',
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
