"""
Unified User Model

Conecta identidades do site e WhatsApp em um único usuário.
NÃO ALTERA modelos existentes - apenas cria relações.
"""
import uuid
from django.db import models


class UnifiedUser(models.Model):
    """
    Usuário unificado - conecta site e WhatsApp.
    
    Um cliente pode:
    - Se cadastrar no site
    - Conversar no WhatsApp
    - E o agente vê tudo junto
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Identificadores únicos
    email = models.EmailField(
        unique=True, 
        null=True, 
        blank=True,
        verbose_name='Email'
    )
    phone_number = models.CharField(
        max_length=20, 
        unique=True, 
        db_index=True,
        verbose_name='Telefone'
    )
    
    # OAuth (Google, etc)
    google_id = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name='Google ID'
    )
    
    # Dados básicos
    name = models.CharField(
        max_length=255,
        verbose_name='Nome'
    )
    profile_picture = models.URLField(
        blank=True,
        verbose_name='Foto de Perfil'
    )
    
    # Dados do site (só leitura, atualizado por signals)
    total_orders = models.PositiveIntegerField(
        default=0,
        verbose_name='Total de Pedidos'
    )
    total_spent = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        verbose_name='Total Gasto'
    )
    last_order_at = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name='Último Pedido em'
    )
    
    # Carrinho abandonado
    has_abandoned_cart = models.BooleanField(
        default=False,
        verbose_name='Tem Carrinho Abandonado'
    )
    abandoned_cart_value = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        verbose_name='Valor do Carrinho'
    )
    abandoned_cart_items = models.JSONField(
        default=list, 
        blank=True,
        verbose_name='Itens do Carrinho'
    )
    abandoned_cart_since = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name='Carrinho Abandonado desde'
    )
    
    # Metadados
    first_seen_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Visto primeiro em'
    )
    last_seen_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Visto última vez em'
    )
    
    # Flags
    is_active = models.BooleanField(
        default=True,
        verbose_name='Ativo'
    )
    
    class Meta:
        db_table = 'unified_users'
        verbose_name = 'Usuário Unificado'
        verbose_name_plural = 'Usuários Unificados'
        ordering = ['-last_seen_at']
    
    def __str__(self):
        return f"{self.name} ({self.phone_number})"
    
    def get_context_for_agent(self) -> str:
        """
        Retorna contexto formatado para o agente AI.
        """
        lines = [
            f"👤 CLIENTE: {self.name}",
        ]
        
        if self.email:
            lines.append(f"📧 Email: {self.email}")
        
        lines.append(f"📊 Total de pedidos: {self.total_orders}")
        lines.append(f"💰 Total gasto: R$ {self.total_spent:.2f}")
        
        if self.last_order_at:
            lines.append(f"🛒 Último pedido: {self.last_order_at.strftime('%d/%m/%Y')}")
        
        if self.has_abandoned_cart and self.abandoned_cart_since:
            from datetime import datetime, timezone
            minutes_ago = (datetime.now(timezone.utc) - self.abandoned_cart_since).total_seconds() / 60
            lines.append(f"🛒⚠️ CARRINHO ABANDONADO há {int(minutes_ago)} minutos!")
            lines.append(f"   Valor: R$ {self.abandoned_cart_value:.2f}")
            if self.abandoned_cart_items:
                items_text = ", ".join([
                    f"{item.get('quantity', 1)}x {item.get('name', 'Item')}"
                    for item in self.abandoned_cart_items[:3]
                ])
                lines.append(f"   Itens: {items_text}")
        
        return "\n".join(lines)


class UnifiedUserActivity(models.Model):
    """
    Log de atividades do usuário.
    Útil para tracking e debug.
    """
    
    class ActivityType(models.TextChoices):
        WHATSAPP_MESSAGE = 'whatsapp_message', 'Mensagem WhatsApp'
        SITE_LOGIN = 'site_login', 'Login no Site'
        SITE_ORDER = 'site_order', 'Pedido no Site'
        CART_UPDATED = 'cart_updated', 'Carrinho Atualizado'
        PROFILE_UPDATED = 'profile_updated', 'Perfil Atualizado'
    
    user = models.ForeignKey(
        UnifiedUser,
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name='Usuário'
    )
    activity_type = models.CharField(
        max_length=50,
        choices=ActivityType.choices,
        verbose_name='Tipo'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Descrição'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadados'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    
    class Meta:
        db_table = 'unified_user_activities'
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'
        ordering = ['-created_at']
