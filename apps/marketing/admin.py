"""
Marketing admin configuration.
"""
from django.contrib import admin
from .models import EmailTemplate, EmailCampaign, EmailRecipient, Subscriber


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'template_type', 'subject', 'created_at']
    list_filter = ['template_type', 'store', 'is_active']
    search_fields = ['name', 'subject']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'status', 'emails_sent', 'emails_opened', 'created_at']
    list_filter = ['status', 'store', 'audience_type']
    search_fields = ['name', 'subject']
    readonly_fields = ['id', 'created_at', 'updated_at', 'started_at', 'completed_at']


@admin.register(EmailRecipient)
class EmailRecipientAdmin(admin.ModelAdmin):
    list_display = ['email', 'campaign', 'status', 'sent_at', 'opened_at']
    list_filter = ['status', 'campaign']
    search_fields = ['email', 'name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'name', 'store', 'status', 'total_orders', 'subscribed_at']
    list_filter = ['status', 'store', 'accepts_marketing']
    search_fields = ['email', 'name', 'phone']
    readonly_fields = ['id', 'created_at', 'updated_at', 'subscribed_at']
