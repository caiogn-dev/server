"""
Campaign API serializers.
"""
from rest_framework import serializers
from ..models import Campaign, CampaignRecipient, ContactList
from apps.automation.models import ScheduledMessage  # Use unified model


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
    """Serializer for ScheduledMessage model (unified from automation app)."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = ScheduledMessage
        fields = [
            'id', 'account', 'account_name', 'to_number', 'contact_name',
            'message_type', 'message_text', 'template_name', 'template_language',
            'template_components', 'media_url', 'buttons', 'content',
            'scheduled_at', 'timezone', 'status', 'status_display',
            'whatsapp_message_id', 'sent_at', 'error_code', 'error_message',
            'is_recurring', 'recurrence_rule', 'next_occurrence',
            'source', 'campaign_id', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'status_display', 'whatsapp_message_id',
            'sent_at', 'error_code', 'error_message',
            'next_occurrence', 'created_at', 'updated_at', 'account_name',
        ]


class ScheduledMessageCreateSerializer(serializers.Serializer):
    """Serializer for creating scheduled messages."""
    account_id = serializers.UUIDField()
    to_number = serializers.CharField(max_length=20)
    contact_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    message_type = serializers.ChoiceField(
        choices=ScheduledMessage.MessageType.choices,
        default=ScheduledMessage.MessageType.TEXT
    )
    message_text = serializers.CharField(required=False, allow_blank=True, default='')
    template_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    template_language = serializers.CharField(max_length=10, default='pt_BR')
    template_components = serializers.ListField(required=False, default=list)
    media_url = serializers.URLField(required=False, allow_blank=True, default='')
    buttons = serializers.ListField(required=False, default=list)
    content = serializers.DictField(required=False, default=dict)
    scheduled_at = serializers.DateTimeField()
    timezone = serializers.CharField(max_length=50, default='America/Sao_Paulo')
    is_recurring = serializers.BooleanField(default=False)
    recurrence_rule = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    metadata = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    source = serializers.CharField(max_length=20, default='manual')


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
