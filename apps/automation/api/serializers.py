"""
Automation API serializers.
"""
from rest_framework import serializers
from ..models import (
    CompanyProfile, AutoMessage, CustomerSession, AutomationLog,
    ScheduledMessage, ReportSchedule, GeneratedReport
)


class CompanyProfileSerializer(serializers.ModelSerializer):
    """Serializer for CompanyProfile.
    
    Includes store data if profile is linked to a store.
    """
    account_phone = serializers.CharField(source='account.phone_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    # Store data (read-only, comes from Store model)
    store_id = serializers.UUIDField(source='store.id', read_only=True)
    store_slug = serializers.CharField(source='store.slug', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    store_email = serializers.CharField(source='store.email', read_only=True)
    store_phone = serializers.CharField(source='store.phone', read_only=True)
    store_whatsapp = serializers.CharField(source='store.whatsapp_number', read_only=True)
    store_address = serializers.CharField(source='store.address', read_only=True)
    store_city = serializers.CharField(source='store.city', read_only=True)
    store_state = serializers.CharField(source='store.state', read_only=True)
    store_type = serializers.CharField(source='store.store_type', read_only=True)
    
    # Computed URLs
    computed_menu_url = serializers.SerializerMethodField()
    computed_order_url = serializers.SerializerMethodField()
    
    class Meta:
        model = CompanyProfile
        fields = [
            'id', 'account', 'account_phone', 'account_name',
            # Store linkage
            'store_id', 'store_slug', 'store_name', 'store_email',
            'store_phone', 'store_whatsapp', 'store_address',
            'store_city', 'store_state', 'store_type',
            # Profile data (may come from store via properties)
            'company_name', 'business_type', 'description',
            'website_url', 'menu_url', 'order_url',
            'computed_menu_url', 'computed_order_url',
            'business_hours',
            # Automation settings
            'auto_reply_enabled', 'welcome_message_enabled', 'menu_auto_send',
            'abandoned_cart_notification', 'abandoned_cart_delay_minutes',
            'pix_notification_enabled', 'payment_confirmation_enabled',
            'order_status_notification_enabled', 'delivery_notification_enabled',
            'external_api_key', 'webhook_secret',
            'use_langflow', 'langflow_flow_id',
            'settings',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'external_api_key', 'webhook_secret', 'created_at', 'updated_at']
    
    def get_computed_menu_url(self, obj):
        return obj.get_menu_url()
    
    def get_computed_order_url(self, obj):
        return obj.get_order_url()


class CreateCompanyProfileSerializer(serializers.Serializer):
    """Serializer for creating a company profile.
    
    If store_id is provided, business data is auto-populated from Store.
    Otherwise, manual data entry is required.
    """
    account_id = serializers.UUIDField()
    store_id = serializers.UUIDField(required=False, allow_null=True)
    
    # Optional: Override store data
    company_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    business_type = serializers.ChoiceField(
        choices=CompanyProfile.BusinessType.choices,
        required=False
    )
    description = serializers.CharField(required=False, allow_blank=True)
    website_url = serializers.URLField(required=False, allow_blank=True)
    menu_url = serializers.URLField(required=False, allow_blank=True)
    order_url = serializers.URLField(required=False, allow_blank=True)
    business_hours = serializers.JSONField(required=False, default=dict)


class UpdateCompanyProfileSerializer(serializers.Serializer):
    """Serializer for updating a company profile."""
    company_name = serializers.CharField(max_length=255, required=False)
    business_type = serializers.ChoiceField(
        choices=CompanyProfile.BusinessType.choices,
        required=False
    )
    description = serializers.CharField(required=False, allow_blank=True)
    website_url = serializers.URLField(required=False, allow_blank=True)
    menu_url = serializers.URLField(required=False, allow_blank=True)
    order_url = serializers.URLField(required=False, allow_blank=True)
    business_hours = serializers.JSONField(required=False)
    
    auto_reply_enabled = serializers.BooleanField(required=False)
    welcome_message_enabled = serializers.BooleanField(required=False)
    menu_auto_send = serializers.BooleanField(required=False)
    
    abandoned_cart_notification = serializers.BooleanField(required=False)
    abandoned_cart_delay_minutes = serializers.IntegerField(required=False, min_value=1)
    
    pix_notification_enabled = serializers.BooleanField(required=False)
    payment_confirmation_enabled = serializers.BooleanField(required=False)
    order_status_notification_enabled = serializers.BooleanField(required=False)
    delivery_notification_enabled = serializers.BooleanField(required=False)
    
    use_langflow = serializers.BooleanField(required=False)
    langflow_flow_id = serializers.UUIDField(required=False, allow_null=True)
    
    settings = serializers.JSONField(required=False)


class AutoMessageSerializer(serializers.ModelSerializer):
    """Serializer for AutoMessage."""
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    
    class Meta:
        model = AutoMessage
        fields = [
            'id', 'company', 'event_type', 'event_type_display', 'name',
            'message_text', 'media_url', 'media_type', 'buttons',
            'is_active', 'delay_seconds', 'conditions', 'priority',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CreateAutoMessageSerializer(serializers.Serializer):
    """Serializer for creating an auto message."""
    company_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=AutoMessage.EventType.choices)
    name = serializers.CharField(max_length=255)
    message_text = serializers.CharField()
    media_url = serializers.URLField(required=False, allow_blank=True)
    media_type = serializers.ChoiceField(
        choices=[('image', 'Image'), ('document', 'Document'), ('video', 'Video')],
        required=False,
        allow_blank=True
    )
    buttons = serializers.JSONField(required=False, default=list)
    is_active = serializers.BooleanField(default=True)
    delay_seconds = serializers.IntegerField(default=0, min_value=0)
    conditions = serializers.JSONField(required=False, default=dict)
    priority = serializers.IntegerField(default=100, min_value=1)


class UpdateAutoMessageSerializer(serializers.Serializer):
    """Serializer for updating an auto message."""
    event_type = serializers.ChoiceField(choices=AutoMessage.EventType.choices, required=False)
    name = serializers.CharField(max_length=255, required=False)
    message_text = serializers.CharField(required=False)
    media_url = serializers.URLField(required=False, allow_blank=True)
    media_type = serializers.ChoiceField(
        choices=[('image', 'Image'), ('document', 'Document'), ('video', 'Video')],
        required=False,
        allow_blank=True
    )
    buttons = serializers.JSONField(required=False)
    is_active = serializers.BooleanField(required=False)
    delay_seconds = serializers.IntegerField(required=False, min_value=0)
    conditions = serializers.JSONField(required=False)
    priority = serializers.IntegerField(required=False, min_value=1)


class CustomerSessionSerializer(serializers.ModelSerializer):
    """Serializer for CustomerSession."""
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = CustomerSession
        fields = [
            'id', 'company', 'company_name',
            'phone_number', 'customer_name', 'customer_email',
            'session_id', 'external_customer_id',
            'status', 'status_display',
            'cart_data', 'cart_total', 'cart_items_count',
            'cart_created_at', 'cart_updated_at',
            'pix_code', 'pix_qr_code', 'pix_expires_at', 'payment_id',
            'order', 'external_order_id',
            'conversation',
            'notifications_sent', 'last_notification_at',
            'last_activity_at', 'expires_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AutomationLogSerializer(serializers.ModelSerializer):
    """Serializer for AutomationLog."""
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    class Meta:
        model = AutomationLog
        fields = [
            'id', 'company', 'company_name', 'session',
            'action_type', 'action_type_display', 'description',
            'phone_number', 'event_type',
            'request_data', 'response_data',
            'is_error', 'error_message',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# Webhook serializers

class CartEventSerializer(serializers.Serializer):
    """Serializer for cart webhook events."""
    session_id = serializers.CharField(max_length=100)
    event_type = serializers.ChoiceField(choices=[
        ('cart_created', 'Cart Created'),
        ('cart_updated', 'Cart Updated'),
        ('cart_abandoned', 'Cart Abandoned'),
    ])
    phone_number = serializers.CharField(max_length=20, required=False)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    items = serializers.ListField(required=False, default=list)
    items_count = serializers.IntegerField(required=False, default=0)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)


class PaymentEventSerializer(serializers.Serializer):
    """Serializer for payment webhook events."""
    session_id = serializers.CharField(max_length=100)
    event_type = serializers.ChoiceField(choices=[
        ('pix_generated', 'PIX Generated'),
        ('payment_confirmed', 'Payment Confirmed'),
        ('payment_failed', 'Payment Failed'),
    ])
    payment_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    order_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    pix_code = serializers.CharField(required=False, allow_blank=True)
    qr_code = serializers.CharField(required=False, allow_blank=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class OrderEventSerializer(serializers.Serializer):
    """Serializer for order webhook events."""
    session_id = serializers.CharField(max_length=100)
    event_type = serializers.ChoiceField(choices=[
        ('order_placed', 'Order Placed'),
        ('order_confirmed', 'Order Confirmed'),
        ('order_preparing', 'Order Preparing'),
        ('order_ready', 'Order Ready'),
        ('order_shipped', 'Order Shipped'),
        ('order_out_for_delivery', 'Out for Delivery'),
        ('order_delivered', 'Order Delivered'),
        ('order_cancelled', 'Order Cancelled'),
    ])
    order_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    order_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tracking_code = serializers.CharField(max_length=100, required=False, allow_blank=True)
    carrier = serializers.CharField(max_length=100, required=False, allow_blank=True)
    delivery_estimate = serializers.CharField(max_length=255, required=False, allow_blank=True)


# Scheduled Message serializers

class ScheduledMessageSerializer(serializers.ModelSerializer):
    """Serializer for ScheduledMessage."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    message_type_display = serializers.CharField(source='get_message_type_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = ScheduledMessage
        fields = [
            'id', 'account', 'account_name',
            'to_number', 'contact_name',
            'message_type', 'message_type_display',
            'message_text', 'template_name', 'template_language', 'template_components',
            'media_url', 'buttons',
            'scheduled_at', 'timezone',
            'status', 'status_display', 'sent_at',
            'whatsapp_message_id', 'error_message',
            'created_by', 'created_by_name', 'notes', 'metadata',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'sent_at', 'whatsapp_message_id', 'error_message', 'created_at', 'updated_at']


class CreateScheduledMessageSerializer(serializers.Serializer):
    """Serializer for creating a scheduled message."""
    account_id = serializers.UUIDField()
    to_number = serializers.CharField(max_length=20)
    contact_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    message_type = serializers.ChoiceField(
        choices=ScheduledMessage.MessageType.choices,
        default='text'
    )
    message_text = serializers.CharField(required=False, allow_blank=True)
    template_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    template_language = serializers.CharField(max_length=10, default='pt_BR')
    template_components = serializers.JSONField(required=False, default=list)
    media_url = serializers.URLField(required=False, allow_blank=True)
    buttons = serializers.JSONField(required=False, default=list)
    scheduled_at = serializers.DateTimeField()
    timezone = serializers.CharField(max_length=50, default='America/Sao_Paulo')
    notes = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class UpdateScheduledMessageSerializer(serializers.Serializer):
    """Serializer for updating a scheduled message."""
    to_number = serializers.CharField(max_length=20, required=False)
    contact_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    message_type = serializers.ChoiceField(
        choices=ScheduledMessage.MessageType.choices,
        required=False
    )
    message_text = serializers.CharField(required=False, allow_blank=True)
    template_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    template_language = serializers.CharField(max_length=10, required=False)
    template_components = serializers.JSONField(required=False)
    media_url = serializers.URLField(required=False, allow_blank=True)
    buttons = serializers.JSONField(required=False)
    scheduled_at = serializers.DateTimeField(required=False)
    timezone = serializers.CharField(max_length=50, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)


# Report Schedule serializers

class ReportScheduleSerializer(serializers.ModelSerializer):
    """Serializer for ReportSchedule."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    report_type_display = serializers.CharField(source='get_report_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = ReportSchedule
        fields = [
            'id', 'name', 'description',
            'report_type', 'report_type_display',
            'account', 'account_name', 'company', 'company_name',
            'frequency', 'frequency_display',
            'day_of_week', 'day_of_month', 'hour', 'timezone',
            'recipients',
            'status', 'status_display',
            'last_run_at', 'next_run_at', 'last_error', 'run_count',
            'created_by', 'created_by_name',
            'include_charts', 'export_format', 'settings',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'last_run_at', 'next_run_at', 'last_error', 'run_count', 'created_at', 'updated_at']


class CreateReportScheduleSerializer(serializers.Serializer):
    """Serializer for creating a report schedule."""
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    report_type = serializers.ChoiceField(
        choices=ReportSchedule.ReportType.choices,
        default='full'
    )
    account_id = serializers.UUIDField(required=False, allow_null=True)
    company_id = serializers.UUIDField(required=False, allow_null=True)
    frequency = serializers.ChoiceField(
        choices=ReportSchedule.Frequency.choices,
        default='weekly'
    )
    day_of_week = serializers.IntegerField(default=1, min_value=1, max_value=7)
    day_of_month = serializers.IntegerField(default=1, min_value=1, max_value=28)
    hour = serializers.IntegerField(default=8, min_value=0, max_value=23)
    timezone = serializers.CharField(max_length=50, default='America/Sao_Paulo')
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        default=list
    )
    include_charts = serializers.BooleanField(default=True)
    export_format = serializers.ChoiceField(
        choices=[('csv', 'CSV'), ('xlsx', 'Excel')],
        default='xlsx'
    )
    settings = serializers.JSONField(required=False, default=dict)


class UpdateReportScheduleSerializer(serializers.Serializer):
    """Serializer for updating a report schedule."""
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    report_type = serializers.ChoiceField(
        choices=ReportSchedule.ReportType.choices,
        required=False
    )
    account_id = serializers.UUIDField(required=False, allow_null=True)
    company_id = serializers.UUIDField(required=False, allow_null=True)
    frequency = serializers.ChoiceField(
        choices=ReportSchedule.Frequency.choices,
        required=False
    )
    day_of_week = serializers.IntegerField(required=False, min_value=1, max_value=7)
    day_of_month = serializers.IntegerField(required=False, min_value=1, max_value=28)
    hour = serializers.IntegerField(required=False, min_value=0, max_value=23)
    timezone = serializers.CharField(max_length=50, required=False)
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        required=False
    )
    status = serializers.ChoiceField(
        choices=ReportSchedule.Status.choices,
        required=False
    )
    include_charts = serializers.BooleanField(required=False)
    export_format = serializers.ChoiceField(
        choices=[('csv', 'CSV'), ('xlsx', 'Excel')],
        required=False
    )
    settings = serializers.JSONField(required=False)


class GeneratedReportSerializer(serializers.ModelSerializer):
    """Serializer for GeneratedReport."""
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = GeneratedReport
        fields = [
            'id', 'schedule', 'schedule_name',
            'name', 'report_type',
            'period_start', 'period_end',
            'status', 'status_display',
            'file_path', 'file_size', 'file_format',
            'records_count', 'generation_time_ms',
            'error_message',
            'email_sent', 'email_sent_at', 'email_recipients',
            'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GenerateReportSerializer(serializers.Serializer):
    """Serializer for generating a report on demand."""
    report_type = serializers.ChoiceField(
        choices=ReportSchedule.ReportType.choices,
        default='full'
    )
    period_start = serializers.DateTimeField(required=False)
    period_end = serializers.DateTimeField(required=False)
    account_id = serializers.UUIDField(required=False, allow_null=True)
    company_id = serializers.UUIDField(required=False, allow_null=True)
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        default=list
    )
    export_format = serializers.ChoiceField(
        choices=[('csv', 'CSV'), ('xlsx', 'Excel')],
        default='xlsx'
    )
