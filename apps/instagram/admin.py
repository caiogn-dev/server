from django.contrib import admin
from django.contrib import messages
from .models import (
    InstagramAccount, InstagramMedia, InstagramMediaItem,
    InstagramProductTag, InstagramCatalog, InstagramProduct,
    InstagramLive, InstagramLiveComment, InstagramConversation,
    InstagramMessage, InstagramScheduledPost, InstagramInsight,
    InstagramWebhookLog
)
from .services import InstagramAPI
from .services.instagram_api import InstagramAPIException


@admin.register(InstagramAccount)
class InstagramAccountAdmin(admin.ModelAdmin):
    list_display = ['username', 'user', 'facebook_page_id', 'has_page_token', 'followers_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'is_verified', 'created_at']
    search_fields = ['username', 'user__email', 'facebook_page_id']
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']
    actions = ['action_refresh_page_token', 'action_sync_account']
    fieldsets = (
        ('Identificadores', {
            'fields': ('user', 'platform', 'username', 'instagram_business_id', 'facebook_page_id'),
        }),
        ('Tokens de Acesso', {
            'fields': ('access_token', 'token_expires_at', 'page_access_token', 'page_token_expires_at'),
            'description': (
                '<strong>access_token</strong>: User/Instagram token (leitura de mídia e insights).<br>'
                '<strong>page_access_token</strong>: Page Access Token da Página Facebook — '
                '<em>obrigatório para enviar mensagens via Instagram Direct</em>. '
                'Se estiver expirado use a action "Renovar Page Access Token" na lista.'
            ),
        }),
        ('Metadados', {
            'fields': ('followers_count', 'follows_count', 'media_count', 'profile_picture_url', 'biography', 'website'),
            'classes': ('collapse',),
        }),
        ('Status', {
            'fields': ('is_active', 'is_verified', 'created_at', 'updated_at', 'last_sync_at'),
        }),
    )

    @admin.display(boolean=True, description='Page Token?')
    def has_page_token(self, obj):
        return bool(obj.page_access_token)

    @admin.action(description='🔑 Renovar Page Access Token (a partir do User Token)')
    def action_refresh_page_token(self, request, queryset):
        ok, fail = 0, 0
        for account in queryset:
            try:
                InstagramAPI(account).refresh_page_token()
                ok += 1
            except InstagramAPIException as exc:
                self.message_user(
                    request,
                    f"@{account.username}: {exc}",
                    level=messages.ERROR,
                )
                fail += 1
        if ok:
            self.message_user(
                request,
                f"Page Access Token renovado com sucesso para {ok} conta(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description='🔄 Sincronizar informações da conta')
    def action_sync_account(self, request, queryset):
        ok = sum(1 for account in queryset if InstagramAPI(account).sync_account_info())
        self.message_user(request, f"{ok} conta(s) sincronizada(s).", level=messages.SUCCESS)


@admin.register(InstagramMedia)
class InstagramMediaAdmin(admin.ModelAdmin):
    list_display = ['account', 'media_type', 'caption_preview', 'status', 'created_at']
    list_filter = ['media_type', 'status', 'created_at']
    search_fields = ['caption', 'account__username']
    readonly_fields = ['created_at', 'updated_at']
    
    def caption_preview(self, obj):
        return obj.caption[:50] + '...' if len(obj.caption) > 50 else obj.caption
    caption_preview.short_description = 'Caption'


@admin.register(InstagramConversation)
class InstagramConversationAdmin(admin.ModelAdmin):
    list_display = ['participant_username', 'account', 'unread_count', 'last_message_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['participant_username', 'participant_name']


@admin.register(InstagramMessage)
class InstagramMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'message_type', 'content_preview', 'is_from_business', 'created_at']
    list_filter = ['message_type', 'is_from_business', 'is_read', 'created_at']
    search_fields = ['content']
    readonly_fields = ['created_at']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(InstagramLive)
class InstagramLiveAdmin(admin.ModelAdmin):
    list_display = ['title', 'account', 'status', 'viewers_count', 'started_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description']


@admin.register(InstagramCatalog)
class InstagramCatalogAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'catalog_id']


@admin.register(InstagramProduct)
class InstagramProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'catalog', 'price', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'product_id']


@admin.register(InstagramScheduledPost)
class InstagramScheduledPostAdmin(admin.ModelAdmin):
    list_display = ['account', 'media_type', 'schedule_time', 'status']
    list_filter = ['status', 'media_type', 'created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InstagramWebhookLog)
class InstagramWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['object_type', 'field', 'is_processed', 'created_at']
    list_filter = ['object_type', 'is_processed', 'created_at']
    readonly_fields = ['created_at']