"""Marketing admin - LEGACY, mantido apenas para compatibilidade.

Use campaigns/admin.py para gerenciar campanhas unificadas.
"""
from django.contrib import admin
from .models import EmailTemplate, EmailCampaign, EmailRecipient, Subscriber


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name']

    def get_model_perms(self, request):
        return {}


@admin.register(EmailRecipient)
class EmailRecipientAdmin(admin.ModelAdmin):
    list_display = ['email', 'campaign', 'status']

    def get_model_perms(self, request):
        return {}


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'template_type']

    def get_model_perms(self, request):
        return {}


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'name', 'store']

    def get_model_perms(self, request):
        return {}
