"""
WhatsApp API serializers.
"""
from rest_framework import serializers
from ..models import WhatsAppAccount, Message, MessageTemplate


class WhatsAppAccountSerializer(serializers.ModelSerializer):
    """Serializer for WhatsApp Account."""
    masked_token = serializers.CharField(read_only=True)
    
    class Meta:
        model = WhatsAppAccount
        fields = [
            'id', 'name', 'phone_number_id', 'waba_id', 'phone_number',
            'display_phone_number', 'status', 'token_version',
            'default_langflow_flow_id', 'auto_response_enabled',
            'human_handoff_enabled', 'metadata', 'masked_token',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'token_version', 'masked_token', 'created_at', 'updated_at'
        ]


class WhatsAppAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating WhatsApp Account."""
    access_token = serializers.CharField(write_only=True)
    
    class Meta:
        model = WhatsAppAccount
        fields = [
            'name', 'phone_number_id', 'waba_id', 'phone_number',
            'display_phone_number', 'access_token', 'webhook_verify_token',
            'default_langflow_flow_id', 'auto_response_enabled',
            'human_handoff_enabled', 'metadata'
        ]

    def create(self, validated_data):
        access_token = validated_data.pop('access_token')
        account = WhatsAppAccount(**validated_data)
        account.access_token = access_token
        account.status = WhatsAppAccount.AccountStatus.ACTIVE
        account.save()
        return account


class WhatsAppAccountUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating WhatsApp Account."""
    access_token = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = WhatsAppAccount
        fields = [
            'name', 'display_phone_number', 'access_token',
            'webhook_verify_token', 'default_langflow_flow_id',
            'auto_response_enabled', 'human_handoff_enabled', 'metadata'
        ]

    def update(self, instance, validated_data):
        access_token = validated_data.pop('access_token', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if access_token:
            instance.access_token = access_token
        
        instance.save()
        return instance


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'account', 'account_name', 'conversation',
            'whatsapp_message_id', 'direction', 'message_type', 'status',
            'from_number', 'to_number', 'content', 'text_body',
            'media_id', 'media_url', 'media_mime_type',
            'template_name', 'template_language', 'context_message_id',
            'sent_at', 'delivered_at', 'read_at', 'failed_at',
            'error_code', 'error_message', 'metadata',
            'processed_by_langflow', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'whatsapp_message_id', 'sent_at', 'delivered_at',
            'read_at', 'failed_at', 'created_at', 'updated_at'
        ]


class SendTextMessageSerializer(serializers.Serializer):
    """Serializer for sending text message."""
    account_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    text = serializers.CharField(max_length=4096)
    preview_url = serializers.BooleanField(default=False)
    reply_to = serializers.CharField(max_length=100, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class SendTemplateMessageSerializer(serializers.Serializer):
    """Serializer for sending template message."""
    account_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    template_name = serializers.CharField(max_length=255)
    language_code = serializers.CharField(max_length=10, default='pt_BR')
    components = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )
    metadata = serializers.JSONField(required=False, default=dict)


class ButtonSerializer(serializers.Serializer):
    """Serializer for interactive button."""
    id = serializers.CharField(max_length=256, required=False)
    title = serializers.CharField(max_length=20)


class SendInteractiveButtonsSerializer(serializers.Serializer):
    """Serializer for sending interactive buttons message."""
    account_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    body_text = serializers.CharField(max_length=1024)
    buttons = ButtonSerializer(many=True, max_length=3)
    header = serializers.DictField(required=False)
    footer = serializers.CharField(max_length=60, required=False, allow_blank=True)
    reply_to = serializers.CharField(max_length=100, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_buttons(self, value):
        if len(value) > 3:
            raise serializers.ValidationError("Maximum 3 buttons allowed")
        if len(value) < 1:
            raise serializers.ValidationError("At least 1 button required")
        return value


class SectionRowSerializer(serializers.Serializer):
    """Serializer for list section row."""
    id = serializers.CharField(max_length=200)
    title = serializers.CharField(max_length=24)
    description = serializers.CharField(max_length=72, required=False, allow_blank=True)


class SectionSerializer(serializers.Serializer):
    """Serializer for list section."""
    title = serializers.CharField(max_length=24, required=False, allow_blank=True)
    rows = SectionRowSerializer(many=True)


class SendInteractiveListSerializer(serializers.Serializer):
    """Serializer for sending interactive list message."""
    account_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    body_text = serializers.CharField(max_length=1024)
    button_text = serializers.CharField(max_length=20)
    sections = SectionSerializer(many=True)
    header = serializers.CharField(max_length=60, required=False, allow_blank=True)
    footer = serializers.CharField(max_length=60, required=False, allow_blank=True)
    reply_to = serializers.CharField(max_length=100, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_sections(self, value):
        if len(value) > 10:
            raise serializers.ValidationError("Maximum 10 sections allowed")
        if len(value) < 1:
            raise serializers.ValidationError("At least 1 section required")
        
        total_rows = sum(len(section.get('rows', [])) for section in value)
        if total_rows > 10:
            raise serializers.ValidationError("Maximum 10 rows total allowed")
        
        return value


class SendImageSerializer(serializers.Serializer):
    """Serializer for sending image message."""
    account_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    image_url = serializers.URLField(required=False, allow_blank=True)
    image_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    caption = serializers.CharField(max_length=1024, required=False, allow_blank=True)
    reply_to = serializers.CharField(max_length=100, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, data):
        if not data.get('image_url') and not data.get('image_id'):
            raise serializers.ValidationError(
                "Either image_url or image_id must be provided"
            )
        return data


class SendDocumentSerializer(serializers.Serializer):
    """Serializer for sending document message."""
    account_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    document_url = serializers.URLField(required=False, allow_blank=True)
    document_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    filename = serializers.CharField(max_length=255, required=False, allow_blank=True)
    caption = serializers.CharField(max_length=1024, required=False, allow_blank=True)
    reply_to = serializers.CharField(max_length=100, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, data):
        if not data.get('document_url') and not data.get('document_id'):
            raise serializers.ValidationError(
                "Either document_url or document_id must be provided"
            )
        return data


class MessageTemplateSerializer(serializers.ModelSerializer):
    """Serializer for Message Template."""
    
    class Meta:
        model = MessageTemplate
        fields = [
            'id', 'account', 'template_id', 'name', 'language',
            'category', 'status', 'components', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MarkAsReadSerializer(serializers.Serializer):
    """Serializer for marking message as read."""
    account_id = serializers.UUIDField()
    message_id = serializers.CharField(max_length=100)


class ConversationHistorySerializer(serializers.Serializer):
    """Serializer for conversation history request."""
    account_id = serializers.UUIDField()
    phone_number = serializers.CharField(max_length=20)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)


class MessageStatsSerializer(serializers.Serializer):
    """Serializer for message statistics request."""
    account_id = serializers.UUIDField()
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
