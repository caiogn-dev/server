from django.contrib import admin
from .models import CompanyProfile, AutoMessage, CustomerSession, AutomationLog


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'account', 'store', 'auto_reply_enabled', 'created_at']
    list_filter = ['auto_reply_enabled', 'use_langflow', 'created_at']
    search_fields = ['company_name', 'account__phone_number', 'store__name']
    readonly_fields = ['external_api_key', 'webhook_secret', 'company_name', 'business_type']
    
    fieldsets = (
        ('Store Linkage', {
            'fields': ('account', 'store'),
        }),
        ('Business Info (from Store)', {
            'fields': ('company_name', 'business_type', 'description'),
            'classes': ('collapse',),
        }),
        ('URLs', {
            'fields': ('website_url', 'menu_url', 'order_url'),
        }),
        ('Automation Settings', {
            'fields': ('auto_reply_enabled', 'welcome_message_enabled', 'menu_auto_send'),
        }),
        ('Notifications', {
            'fields': (
                'abandoned_cart_notification', 'abandoned_cart_delay_minutes',
                'pix_notification_enabled', 'payment_confirmation_enabled',
                'order_status_notification_enabled', 'delivery_notification_enabled'
            ),
        }),
        ('Integrations', {
            'fields': ('external_api_key', 'webhook_secret', 'use_langflow', 'langflow_flow_id'),
        }),
        ('Advanced', {
            'fields': ('business_hours', 'settings'),
            'classes': ('collapse',),
        }),
    )


@admin.register(AutoMessage)
class AutoMessageAdmin(admin.ModelAdmin):
    list_display = ['company', 'event_type', 'name', 'is_active', 'priority']
    list_filter = ['event_type', 'is_active', 'company']
    search_fields = ['name', 'message_text']


@admin.register(CustomerSession)
class CustomerSessionAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'company', 'status', 'cart_total', 'last_activity_at']
    list_filter = ['status', 'company']
    search_fields = ['phone_number', 'session_id', 'customer_name']
    readonly_fields = ['notifications_sent']


@admin.register(AutomationLog)
class AutomationLogAdmin(admin.ModelAdmin):
    list_display = ['company', 'action_type', 'phone_number', 'is_error', 'created_at']
    list_filter = ['action_type', 'is_error', 'company']
    search_fields = ['description', 'phone_number']
    readonly_fields = ['request_data', 'response_data']
