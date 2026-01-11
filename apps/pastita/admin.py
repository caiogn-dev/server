"""
Pastita Admin Configuration
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import (
    CustomUser, Produto, Molho, Carne, Rondelli, Combo,
    Carrinho, ItemCarrinho, ItemComboCarrinho,
    Pedido, ItemPedido, ItemComboPedido
)


# =============================================================================
# USER ADMIN
# =============================================================================

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informações Pessoais', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas', {'fields': ('last_login',)}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone'),
        }),
    )


# =============================================================================
# PRODUTO ADMIN
# =============================================================================

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco_formatado', 'ativo', 'imagem_preview', 'criado_em')
    list_filter = ('ativo', 'criado_em')
    search_fields = ('nome', 'descricao')
    list_editable = ('ativo',)
    ordering = ('-criado_em',)
    
    def preco_formatado(self, obj):
        return f"R$ {obj.preco:.2f}"
    preco_formatado.short_description = "Preço"
    
    def imagem_preview(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />', obj.imagem.url)
        return "-"
    imagem_preview.short_description = "Imagem"


@admin.register(Molho)
class MolhoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'tipo', 'quantidade', 'preco_formatado', 'ativo')
    list_filter = ('tipo', 'ativo')
    search_fields = ('nome', 'tipo')
    list_editable = ('ativo',)
    
    def preco_formatado(self, obj):
        return f"R$ {obj.preco:.2f}"
    preco_formatado.short_description = "Preço"


@admin.register(Carne)
class CarneAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'tipo', 'quantidade', 'preco_formatado', 'molhos_count', 'ativo')
    list_filter = ('tipo', 'ativo')
    search_fields = ('nome', 'tipo')
    list_editable = ('ativo',)
    filter_horizontal = ('molhos',)
    
    def preco_formatado(self, obj):
        return f"R$ {obj.preco:.2f}"
    preco_formatado.short_description = "Preço"
    
    def molhos_count(self, obj):
        return obj.molhos.count()
    molhos_count.short_description = "Molhos"


@admin.register(Rondelli)
class RondelliAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'sabor', 'categoria', 'quantidade', 'preco_formatado', 'ativo')
    list_filter = ('categoria', 'sabor', 'ativo')
    search_fields = ('nome', 'sabor')
    list_editable = ('ativo',)
    
    def preco_formatado(self, obj):
        return f"R$ {obj.preco:.2f}"
    preco_formatado.short_description = "Preço"


@admin.register(Combo)
class ComboAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco_formatado', 'economia_formatada', 'rondelli', 'carne', 'destaque', 'ativo')
    list_filter = ('ativo', 'destaque', 'criado_em')
    search_fields = ('nome', 'descricao')
    list_editable = ('ativo', 'destaque')
    filter_horizontal = ('molhos',)
    
    fieldsets = (
        (None, {'fields': ('nome', 'descricao', 'imagem')}),
        ('Componentes', {'fields': ('rondelli', 'carne', 'molhos')}),
        ('Preços', {'fields': ('preco', 'preco_original')}),
        ('Status', {'fields': ('ativo', 'destaque')}),
    )
    
    def preco_formatado(self, obj):
        return f"R$ {obj.preco:.2f}"
    preco_formatado.short_description = "Preço"
    
    def economia_formatada(self, obj):
        if obj.economia > 0:
            return format_html('<span style="color: green;">R$ {:.2f} ({}%)</span>', obj.economia, obj.percentual_desconto)
        return "-"
    economia_formatada.short_description = "Economia"


# =============================================================================
# CARRINHO ADMIN
# =============================================================================

class ItemCarrinhoInline(admin.TabularInline):
    model = ItemCarrinho
    extra = 0
    readonly_fields = ('subtotal_formatado',)
    
    def subtotal_formatado(self, obj):
        return f"R$ {obj.subtotal:.2f}"
    subtotal_formatado.short_description = "Subtotal"


class ItemComboCarrinhoInline(admin.TabularInline):
    model = ItemComboCarrinho
    extra = 0
    readonly_fields = ('subtotal_formatado',)
    
    def subtotal_formatado(self, obj):
        return f"R$ {obj.subtotal:.2f}"
    subtotal_formatado.short_description = "Subtotal"


@admin.register(Carrinho)
class CarrinhoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'quantidade_itens', 'total_formatado', 'atualizado_em')
    search_fields = ('usuario__email',)
    inlines = [ItemCarrinhoInline, ItemComboCarrinhoInline]
    
    def total_formatado(self, obj):
        return f"R$ {obj.total:.2f}"
    total_formatado.short_description = "Total"


# =============================================================================
# PEDIDO ADMIN
# =============================================================================

class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = ('subtotal_formatado',)
    
    def subtotal_formatado(self, obj):
        return f"R$ {obj.subtotal:.2f}"
    subtotal_formatado.short_description = "Subtotal"


class ItemComboPedidoInline(admin.TabularInline):
    model = ItemComboPedido
    extra = 0
    readonly_fields = ('subtotal_formatado',)
    
    def subtotal_formatado(self, obj):
        return f"R$ {obj.subtotal:.2f}"
    subtotal_formatado.short_description = "Subtotal"


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'status_badge', 'total_formatado', 'payment_id', 'criado_em')
    list_filter = ('status', 'criado_em')
    search_fields = ('usuario__email', 'payment_id', 'preference_id')
    readonly_fields = ('criado_em', 'atualizado_em', 'data_pagamento')
    inlines = [ItemPedidoInline, ItemComboPedidoInline]
    
    fieldsets = (
        (None, {'fields': ('usuario', 'status')}),
        ('Pagamento', {'fields': ('payment_id', 'preference_id', 'total', 'data_pagamento')}),
        ('Entrega', {'fields': ('endereco_entrega', 'observacoes')}),
        ('Datas', {'fields': ('criado_em', 'atualizado_em')}),
    )
    
    def total_formatado(self, obj):
        return f"R$ {obj.total:.2f}"
    total_formatado.short_description = "Total"
    
    def status_badge(self, obj):
        colors = {
            'pendente': '#FEF3C7',
            'processando': '#DBEAFE',
            'aprovado': '#D1FAE5',
            'pago': '#D1FAE5',
            'preparando': '#E9D5FF',
            'enviado': '#C7D2FE',
            'entregue': '#D1FAE5',
            'cancelado': '#FEE2E2',
            'falhou': '#FEE2E2',
        }
        bg = colors.get(obj.status, '#F3F4F6')
        return format_html(
            '<span style="background: {}; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{}</span>',
            bg, obj.get_status_display()
        )
    status_badge.short_description = "Status"
