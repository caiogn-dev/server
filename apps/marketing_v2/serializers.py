""" Marketing v2 - Serializers. """
from rest_framework import serializers
from .models import Campaign, Template, Automation, ScheduledMessage


class CampaignSerializer(serializers.ModelSerializer):
    """Serializer para campanhas."""
    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'description', 'channel', 'subject', 'content',
            'audience_type', 'audience_filters', 'status', 'scheduled_at',
            'total_recipients', 'sent_count', 'delivered_count', 'read_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TemplateSerializer(serializers.ModelSerializer):
    """Serializer para templates."""
    class Meta:
        model = Template
        fields = [
            'id', 'name', 'channel', 'content', 'variables',
            'whatsapp_template_name', 'whatsapp_status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AutomationSerializer(serializers.ModelSerializer):
    """Serializer para automações."""
    class Meta:
        model = Automation
        fields = [
            'id', 'name', 'trigger', 'actions', 'conditions',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ScheduledMessageSerializer(serializers.ModelSerializer):
    """Serializer para mensagens agendadas."""
    class Meta:
        model = ScheduledMessage
        fields = [
            'id', 'recipient', 'channel', 'content',
            'scheduled_at', 'status', 'sent_at', 'error_message',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
