from django.contrib import admin
from .models import Agent, AgentConversation, AgentMessage


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider', 'model_name', 'status', 'created_at']
    list_filter = ['provider', 'status', 'is_active']
    search_fields = ['name', 'description']
    filter_horizontal = ['accounts']
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('name', 'description', 'status')
        }),
        ('Configuração do Modelo', {
            'fields': ('provider', 'model_name', 'api_key', 'base_url')
        }),
        ('Parâmetros', {
            'fields': ('temperature', 'max_tokens', 'timeout')
        }),
        ('Prompt', {
            'fields': ('system_prompt', 'context_prompt')
        }),
        ('Memória', {
            'fields': ('use_memory', 'memory_ttl')
        }),
        ('Contas WhatsApp', {
            'fields': ('accounts',)
        }),
    )


@admin.register(AgentConversation)
class AgentConversationAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'agent', 'phone_number', 'message_count', 'last_message_at']
    list_filter = ['agent', 'created_at']
    search_fields = ['session_id', 'phone_number']


@admin.register(AgentMessage)
class AgentMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at']
    
    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Conteúdo'
