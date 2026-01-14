"""
Marketing API serializers.
"""
from rest_framework import serializers
from apps.marketing.models import EmailTemplate, EmailCampaign, EmailRecipient, Subscriber


class EmailTemplateSerializer(serializers.ModelSerializer):
    """Serializer for email templates."""
    
    class Meta:
        model = EmailTemplate
        fields = [
            'id', 'store', 'name', 'description', 'template_type',
            'subject', 'html_content', 'text_content', 'preview_text',
            'thumbnail_url', 'variables', 'created_by', 'created_at',
            'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class EmailTemplateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for template lists."""
    
    class Meta:
        model = EmailTemplate
        fields = ['id', 'name', 'template_type', 'subject', 'preview_text', 'thumbnail_url', 'created_at']


class EmailCampaignSerializer(serializers.ModelSerializer):
    """Serializer for email campaigns."""
    
    template_name = serializers.CharField(source='template.name', read_only=True)
    open_rate = serializers.FloatField(read_only=True)
    click_rate = serializers.FloatField(read_only=True)
    
    # Make template optional (can be null)
    template = serializers.PrimaryKeyRelatedField(
        queryset=EmailTemplate.objects.all(),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = EmailCampaign
        fields = [
            'id', 'store', 'name', 'description', 'template', 'template_name',
            'subject', 'html_content', 'text_content', 'from_name', 'from_email',
            'reply_to', 'audience_type', 'audience_filters', 'recipient_list',
            'status', 'scheduled_at', 'started_at', 'completed_at',
            'total_recipients', 'emails_sent', 'emails_delivered',
            'emails_opened', 'emails_clicked', 'emails_bounced',
            'emails_unsubscribed', 'open_rate', 'click_rate',
            'created_by', 'metadata', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'created_by', 'created_at', 'updated_at',
            'started_at', 'completed_at', 'total_recipients',
            'emails_sent', 'emails_delivered', 'emails_opened',
            'emails_clicked', 'emails_bounced', 'emails_unsubscribed'
        ]
    
    def validate(self, data):
        """Validate that either template or html_content is provided."""
        template = data.get('template')
        html_content = data.get('html_content')
        
        if not template and not html_content:
            raise serializers.ValidationError({
                'html_content': 'Este campo é obrigatório quando não há template selecionado.'
            })
        
        return data


class EmailCampaignListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for campaign lists."""
    
    open_rate = serializers.FloatField(read_only=True)
    
    class Meta:
        model = EmailCampaign
        fields = [
            'id', 'name', 'subject', 'status', 'scheduled_at',
            'total_recipients', 'emails_sent', 'emails_opened',
            'open_rate', 'created_at'
        ]


class EmailRecipientSerializer(serializers.ModelSerializer):
    """Serializer for email recipients."""
    
    class Meta:
        model = EmailRecipient
        fields = [
            'id', 'campaign', 'email', 'name', 'status',
            'resend_id', 'sent_at', 'delivered_at', 'opened_at',
            'clicked_at', 'error_code', 'error_message', 'variables',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SubscriberSerializer(serializers.ModelSerializer):
    """Serializer for subscribers."""
    
    class Meta:
        model = Subscriber
        fields = [
            'id', 'store', 'email', 'name', 'phone', 'status',
            'tags', 'custom_fields', 'source', 'total_orders',
            'total_spent', 'last_order_at', 'accepts_marketing',
            'subscribed_at', 'unsubscribed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'subscribed_at', 'created_at', 'updated_at']


class SubscriberListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for subscriber lists."""
    
    class Meta:
        model = Subscriber
        fields = ['id', 'email', 'name', 'status', 'total_orders', 'total_spent', 'subscribed_at']


class MarketingStatsSerializer(serializers.Serializer):
    """Serializer for marketing statistics."""
    
    campaigns = serializers.DictField()
    emails = serializers.DictField()
    subscribers = serializers.DictField()
    rates = serializers.DictField()


class SendCouponEmailSerializer(serializers.Serializer):
    """Serializer for sending coupon emails."""
    
    to_email = serializers.EmailField()
    customer_name = serializers.CharField(max_length=255)
    coupon_code = serializers.CharField(max_length=50)
    discount_value = serializers.CharField(max_length=50)
    expiry_date = serializers.CharField(max_length=50, required=False, allow_blank=True)


class SendWelcomeEmailSerializer(serializers.Serializer):
    """Serializer for sending welcome emails."""
    
    to_email = serializers.EmailField()
    customer_name = serializers.CharField(max_length=255)


class SendCampaignSerializer(serializers.Serializer):
    """Serializer for sending a campaign."""
    
    campaign_id = serializers.UUIDField()
