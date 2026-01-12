from django.contrib import admin
from .models import Campaign, CampaignRecipient, ScheduledMessage, ContactList


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'campaign_type', 'status', 'total_recipients', 'messages_sent', 'created_at']
    list_filter = ['status', 'campaign_type', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'campaign', 'status', 'sent_at', 'delivered_at']
    list_filter = ['status', 'created_at']
    search_fields = ['phone_number', 'contact_name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ScheduledMessage)
class ScheduledMessageAdmin(admin.ModelAdmin):
    list_display = ['to_number', 'account', 'message_type', 'status', 'scheduled_at']
    list_filter = ['status', 'message_type', 'scheduled_at']
    search_fields = ['to_number', 'contact_name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ContactList)
class ContactListAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'contact_count', 'source', 'created_at']
    list_filter = ['source', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
