"""
Admin configuration for webhooks including Dead Letter Queue and Outbox.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count
from .models import (
    WebhookEvent, 
    WebhookEndpoint, 
    WebhookDeliveryAttempt,
    WebhookDeadLetter,
    WebhookOutbox,
)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'provider', 'event_type', 'status', 'created_at', 'store']
    list_filter = ['provider', 'status', 'created_at']
    search_fields = ['event_id', 'event_type', 'error_message']
    readonly_fields = ['created_at', 'updated_at', 'processed_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('provider', 'event_type', 'event_id', 'store')
        }),
        ('Request Data', {
            'fields': ('payload', 'headers', 'query_params'),
            'classes': ('collapse',)
        }),
        ('Processing', {
            'fields': ('status', 'processed_at', 'retry_count', 'handler_result')
        }),
        ('Security', {
            'fields': ('signature_valid', 'signature_algorithm'),
            'classes': ('collapse',)
        }),
        ('Error Info', {
            'fields': ('error_message', 'error_traceback'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider', 'path', 'is_active', 'total_received', 'total_failed']
    list_filter = ['provider', 'is_active']
    search_fields = ['name', 'path']
    
    fieldsets = (
        ('Identification', {
            'fields': ('name', 'provider', 'path', 'handler_class')
        }),
        ('Security', {
            'fields': ('secret', 'verify_token', 'signature_header'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'log_payloads')
        }),
        ('Stats', {
            'fields': ('total_received', 'total_processed', 'total_failed', 
                      'last_received_at', 'last_error_at', 'last_error'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['total_received', 'total_processed', 'total_failed', 
                      'last_received_at', 'last_error_at', 'last_error']


@admin.register(WebhookDeliveryAttempt)
class WebhookDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'endpoint_url_short', 'event_type', 'status', 'attempt_number', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['endpoint_url', 'event_type', 'error_message']
    readonly_fields = ['created_at', 'updated_at']
    
    def endpoint_url_short(self, obj):
        return obj.endpoint_url[:50] + '...' if len(obj.endpoint_url) > 50 else obj.endpoint_url
    endpoint_url_short.short_description = 'Endpoint URL'


# =============================================================================
# DEAD LETTER QUEUE ADMIN
# =============================================================================

@admin.register(WebhookDeadLetter)
class WebhookDeadLetterAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'provider', 'event_type', 'status_badge', 
        'failure_reason', 'retry_count', 'created_at', 'actions_column'
    ]
    list_filter = ['status', 'failure_reason', 'provider', 'created_at']
    search_fields = ['event_id', 'event_type', 'error_message', 'failure_signature']
    readonly_fields = [
        'created_at', 'updated_at', 'reprocessed_at', 
        'failure_signature', 'reprocessing_result'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('original_event', 'provider', 'event_type', 'event_id')
        }),
        ('Payload', {
            'fields': ('payload', 'headers', 'query_params'),
            'classes': ('collapse',)
        }),
        ('Failure Details', {
            'fields': ('status', 'failure_reason', 'failure_signature', 
                      'error_message', 'error_traceback')
        }),
        ('Retry Info', {
            'fields': ('retry_count', 'max_retries_reached', 'last_retry_at')
        }),
        ('Reprocessing', {
            'fields': ('reprocessed_at', 'reprocessed_by', 'reprocessing_result')
        }),
        ('Context', {
            'fields': ('store',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['reprocess_selected', 'discard_selected', 'reprocess_by_signature']
    
    def status_badge(self, obj):
        colors = {
            WebhookDeadLetter.Status.FAILED: 'red',
            WebhookDeadLetter.Status.REPROCESSING: 'orange',
            WebhookDeadLetter.Status.RESOLVED: 'green',
            WebhookDeadLetter.Status.DISCARDED: 'gray',
        }
        return format_html(
            '<span style="color: {};">●</span> {}',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def actions_column(self, obj):
        """Add action buttons to the admin list view."""
        if not obj.can_reprocess():
            return '-'
        
        reprocess_url = reverse('admin:webhooks_webhookdeadletter_reprocess', args=[obj.id])
        return format_html(
            '<a class="button" href="{}">Reprocess</a>',
            reprocess_url
        )
    actions_column.short_description = 'Actions'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<uuid:pk>/reprocess/',
                self.admin_site.admin_view(self.reprocess_view),
                name='webhooks_webhookdeadletter_reprocess',
            ),
            path(
                'reprocess-by-signature/',
                self.admin_site.admin_view(self.reprocess_by_signature_view),
                name='webhooks_webhookdeadletter_reprocess_by_signature',
            ),
        ]
        return custom_urls + urls
    
    def reprocess_view(self, request, pk):
        """Handle single entry reprocessing."""
        from .tasks import reprocess_dead_letter_entry
        
        entry = get_object_or_404(WebhookDeadLetter, pk=pk)
        
        if not entry.can_reprocess():
            messages.error(request, f"Entry {pk} cannot be reprocessed (status: {entry.status})")
            return redirect('admin:webhooks_webhookdeadletter_changelist')
        
        try:
            reprocess_dead_letter_entry.delay(str(pk), request.user.id)
            messages.success(request, f"Reprocessing started for entry {pk}")
        except Exception as e:
            messages.error(request, f"Failed to start reprocessing: {e}")
        
        return redirect('admin:webhooks_webhookdeadletter_changelist')
    
    def reprocess_by_signature_view(self, request):
        """Handle reprocessing by failure signature."""
        from .tasks import reprocess_by_failure_signature
        
        signature = request.GET.get('signature')
        if not signature:
            messages.error(request, "No failure signature provided")
            return redirect('admin:webhooks_webhookdeadletter_changelist')
        
        try:
            reprocess_by_failure_signature.delay(signature, request.user.id)
            messages.success(request, f"Reprocessing started for signature: {signature}")
        except Exception as e:
            messages.error(request, f"Failed to start reprocessing: {e}")
        
        return redirect('admin:webhooks_webhookdeadletter_changelist')
    
    def reprocess_selected(self, request, queryset):
        """Admin action to reprocess selected entries."""
        from .tasks import reprocess_dead_letter_entry
        
        count = 0
        for entry in queryset.filter(status=WebhookDeadLetter.Status.FAILED):
            try:
                reprocess_dead_letter_entry.delay(str(entry.id), request.user.id)
                count += 1
            except Exception as e:
                messages.error(request, f"Failed to reprocess {entry.id}: {e}")
        
        messages.success(request, f"{count} entries queued for reprocessing")
    reprocess_selected.short_description = "Reprocess selected entries"
    
    def discard_selected(self, request, queryset):
        """Admin action to discard selected entries."""
        count = queryset.filter(
            status=WebhookDeadLetter.Status.FAILED
        ).update(status=WebhookDeadLetter.Status.DISCARDED)
        messages.success(request, f"{count} entries marked as discarded")
    discard_selected.short_description = "Discard selected entries"
    
    def reprocess_by_signature(self, request, queryset):
        """Admin action to reprocess entries with same failure signature."""
        from .tasks import reprocess_by_failure_signature
        
        # Get unique signatures from selected entries
        signatures = set(
            queryset.values_list('failure_signature', flat=True)
            .distinct()
        )
        
        count = 0
        for signature in signatures:
            if signature:
                try:
                    reprocess_by_failure_signature.delay(signature, request.user.id)
                    count += 1
                except Exception as e:
                    messages.error(request, f"Failed to process signature {signature}: {e}")
        
        messages.success(request, f"Reprocessing queued for {count} failure signatures")
    reprocess_by_signature.short_description = "Reprocess all with same failure signature"
    
    def changelist_view(self, request, extra_context=None):
        """Add summary statistics to the changelist view."""
        # Get failure statistics
        failure_stats = (
            WebhookDeadLetter.objects
            .filter(status=WebhookDeadLetter.Status.FAILED)
            .values('failure_reason')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Get top failure signatures
        signature_stats = (
            WebhookDeadLetter.objects
            .filter(status=WebhookDeadLetter.Status.FAILED)
            .values('failure_signature', 'error_message')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        
        extra_context = extra_context or {}
        extra_context['failure_stats'] = failure_stats
        extra_context['signature_stats'] = signature_stats
        
        return super().changelist_view(request, extra_context=extra_context)


# =============================================================================
# OUTBOX ADMIN
# =============================================================================

@admin.register(WebhookOutbox)
class WebhookOutboxAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'event_type', 'status_badge', 'priority', 
        'retry_count', 'endpoint_url_short', 'created_at'
    ]
    list_filter = ['status', 'priority', 'created_at', 'event_type']
    search_fields = ['idempotency_key', 'event_type', 'error_message', 'endpoint_url']
    readonly_fields = [
        'created_at', 'updated_at', 'processed_at', 
        'processing_started_at', 'generate_signature_display'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Event', {
            'fields': ('event_type', 'payload', 'priority', 'idempotency_key')
        }),
        ('Target', {
            'fields': ('endpoint_url', 'headers', 'secret', 'generate_signature_display')
        }),
        ('Status', {
            'fields': ('status', 'scheduled_at')
        }),
        ('Processing', {
            'fields': ('processed_at', 'processing_started_at', 'retry_count', 'max_retries', 'next_retry_at')
        }),
        ('Result', {
            'fields': ('http_status', 'response_body', 'error_message')
        }),
        ('Context', {
            'fields': ('store', 'source_model', 'source_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['retry_selected', 'mark_as_failed', 'process_immediately']
    
    def status_badge(self, obj):
        colors = {
            WebhookOutbox.Status.PENDING: 'blue',
            WebhookOutbox.Status.PROCESSING: 'orange',
            WebhookOutbox.Status.SENT: 'green',
            WebhookOutbox.Status.FAILED: 'red',
            WebhookOutbox.Status.SCHEDULED: 'purple',
        }
        return format_html(
            '<span style="color: {};">●</span> {}',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def endpoint_url_short(self, obj):
        return obj.endpoint_url[:50] + '...' if len(obj.endpoint_url) > 50 else obj.endpoint_url
    endpoint_url_short.short_description = 'Endpoint'
    
    def generate_signature_display(self, obj):
        """Display generated signature for debugging."""
        if not obj.secret:
            return "No secret configured"
        return format_html('<code>{}</code>', obj.generate_signature())
    generate_signature_display.short_description = 'Generated Signature'
    
    def retry_selected(self, request, queryset):
        """Admin action to retry selected outbox entries."""
        from .tasks import process_outbox_entry
        
        count = 0
        for entry in queryset.filter(
            status__in=[WebhookOutbox.Status.FAILED, WebhookOutbox.Status.SCHEDULED]
        ):
            entry.status = WebhookOutbox.Status.PENDING
            entry.retry_count = 0
            entry.error_message = ''
            entry.save(update_fields=['status', 'retry_count', 'error_message', 'updated_at'])
            
            try:
                process_outbox_entry.delay(str(entry.id))
                count += 1
            except Exception as e:
                messages.error(request, f"Failed to retry {entry.id}: {e}")
        
        messages.success(request, f"{count} entries queued for retry")
    retry_selected.short_description = "Retry selected entries"
    
    def mark_as_failed(self, request, queryset):
        """Admin action to mark entries as failed."""
        count = queryset.exclude(status=WebhookOutbox.Status.SENT).update(
            status=WebhookOutbox.Status.FAILED,
            error_message='Manually marked as failed by admin'
        )
        messages.success(request, f"{count} entries marked as failed")
    mark_as_failed.short_description = "Mark as failed (skip processing)"
    
    def process_immediately(self, request, queryset):
        """Admin action to process entries immediately."""
        from .tasks import process_outbox_entry
        
        count = 0
        for entry in queryset.filter(status=WebhookOutbox.Status.PENDING):
            try:
                process_outbox_entry.delay(str(entry.id))
                entry.status = WebhookOutbox.Status.PROCESSING
                entry.save(update_fields=['status', 'updated_at'])
                count += 1
            except Exception as e:
                messages.error(request, f"Failed to process {entry.id}: {e}")
        
        messages.success(request, f"{count} entries queued for immediate processing")
    process_immediately.short_description = "Process immediately"
