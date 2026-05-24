from django.contrib import admin
from django.utils.html import format_html
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


class PostadoPostInline(admin.TabularInline):
    model = PostadoPost
    extra = 0
    readonly_fields = ('post_number', 'post_type', 'caption', 'cta', 'hashtags',
                       'feed_preview', 'stories_preview', 'status')
    fields = ('post_number', 'post_type', 'feed_preview', 'caption', 'cta',
              'status', 'revision_notes')

    def feed_preview(self, obj):
        if obj.feed_image_url:
            return format_html('<img src="{}" style="height:120px;"/>', obj.feed_image_url)
        return '—'
    feed_preview.short_description = 'Feed'

    def stories_preview(self, obj):
        if obj.stories_image_url:
            return format_html('<img src="{}" style="height:120px;"/>', obj.stories_image_url)
        return '—'
    stories_preview.short_description = 'Stories'


@admin.register(PostadoPack)
class PostadoPackAdmin(admin.ModelAdmin):
    list_display = ('client', 'month', 'status', 'total_posts', 'generated_at', 'approved_at')
    list_filter = ('status', 'client__niche')
    readonly_fields = ('client', 'month', 'generated_at', 'drive_folder_url')
    inlines = [PostadoPostInline]
    actions = ['mark_delivered']

    def mark_delivered(self, request, queryset):
        from django.utils import timezone
        queryset.update(status=PostadoPack.Status.DELIVERED, delivered_at=timezone.now())
    mark_delivered.short_description = 'Marcar como entregue'


@admin.register(PostadoClient)
class PostadoClientAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'niche', 'tone', 'status', 'email', 'created_at')
    list_filter = ('niche', 'status')
    search_fields = ('business_name', 'email')


@admin.register(PostadoPost)
class PostadoPostAdmin(admin.ModelAdmin):
    list_display = ('pack', 'post_number', 'post_type', 'status', 'feed_preview_small')
    list_filter = ('status', 'post_type', 'pack__client__niche')
    search_fields = ('pack__client__business_name',)
    actions = ['approve_posts', 'reject_posts']

    def feed_preview_small(self, obj):
        if obj.feed_image_url:
            return format_html('<img src="{}" style="height:60px;"/>', obj.feed_image_url)
        return '—'
    feed_preview_small.short_description = 'Preview'

    def approve_posts(self, request, queryset):
        queryset.update(status=PostadoPost.Status.APPROVED)
    approve_posts.short_description = 'Aprovar posts selecionados'

    def reject_posts(self, request, queryset):
        queryset.update(status=PostadoPost.Status.REJECTED)
    reject_posts.short_description = 'Rejeitar posts selecionados'
