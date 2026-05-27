from django.contrib import admin
from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'city', 'business_type', 'status', 'created_at']
    list_filter = ['status', 'business_type', 'created_at']
    search_fields = ['name', 'phone', 'email', 'city']
    list_editable = ['status']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']
