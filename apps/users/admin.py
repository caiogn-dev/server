"""
Admin for UnifiedUser and UnifiedUserActivity.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import UnifiedUser, UnifiedUserActivity


class UnifiedUserActivityInline(admin.TabularInline):
    model = UnifiedUserActivity
    extra = 0
    readonly_fields = ('activity_type', 'description', 'metadata', 'created_at')
    can_delete = False
    max_num = 20
    ordering = ('-created_at',)


@admin.register(UnifiedUser)
class UnifiedUserAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'phone_number', 'email', 'total_orders',
        'total_spent_display', 'has_abandoned_cart', 'is_active', 'last_seen_at',
    )
    list_filter = ('is_active', 'has_abandoned_cart')
    search_fields = ('name', 'phone_number', 'email', 'google_id')
    readonly_fields = ('id', 'first_seen_at', 'last_seen_at')
    ordering = ('-last_seen_at',)
    inlines = [UnifiedUserActivityInline]

    fieldsets = (
        ('Identidade', {
            'fields': ('id', 'name', 'phone_number', 'email', 'google_id', 'profile_picture'),
        }),
        ('Pedidos', {
            'fields': ('total_orders', 'total_spent', 'last_order_at'),
        }),
        ('Carrinho Abandonado', {
            'fields': (
                'has_abandoned_cart', 'abandoned_cart_value',
                'abandoned_cart_items', 'abandoned_cart_since',
            ),
            'classes': ('collapse',),
        }),
        ('Metadados', {
            'fields': ('is_active', 'first_seen_at', 'last_seen_at'),
        }),
    )

    def total_spent_display(self, obj):
        return f'R$ {obj.total_spent:.2f}'
    total_spent_display.short_description = 'Total Gasto'


@admin.register(UnifiedUserActivity)
class UnifiedUserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'description', 'created_at')
    list_filter = ('activity_type',)
    search_fields = ('user__name', 'user__phone_number', 'description')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
