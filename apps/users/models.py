"""
Unified User Model

Identidade canônica de qualquer pessoa no Pastita (cliente, prospect, usuário).
Conecta WhatsApp, site e checkout em um único registro sem duplicatas.
"""
import uuid
from django.conf import settings
from django.db import models, transaction


class UnifiedUser(models.Model):
    """
    Usuário unificado - conecta site e WhatsApp.
    
    Um cliente pode:
    - Se cadastrar no site
    - Conversar no WhatsApp
    - E o agente vê tudo junto
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Vínculo com Django User (auth system)
    django_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unified_profile',
        verbose_name='Django User',
        help_text='Usuário Django correspondente (login no dashboard/site)',
    )

    # Identificadores únicos
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
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

    # ── Canonical lookup ───────────────────────────────────────────────────────

    @classmethod
    def _normalize_phone(cls, phone: str) -> str:
        """Returns normalized E.164-like phone without '+' prefix."""
        from apps.core.utils import normalize_phone_number
        return normalize_phone_number(phone) if phone else ""

    @classmethod
    def _phone_candidates(cls, phone: str) -> list[str]:
        """All plausible formats for the same phone, for lookup."""
        from apps.core.utils import normalize_phone_number
        digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
        if not digits:
            return []
        norm = normalize_phone_number(digits)
        candidates = [phone, digits, norm, f"+{digits}", f"+{norm}"]
        if norm.startswith("55") and len(norm) > 11:
            local = norm[2:]
            candidates += [local, f"+{local}"]
        return list(dict.fromkeys(c for c in candidates if c))

    @classmethod
    @transaction.atomic
    def resolve(
        cls,
        phone: str = "",
        email: str = "",
        name: str = "",
        django_user=None,
    ) -> tuple["UnifiedUser", bool]:
        """
        Canonical get-or-create. Checks by (1) django_user, (2) email,
        (3) normalized phone before creating — never duplicates the same person.

        Returns (user, created).
        """
        # 1. By django_user (most precise)
        if django_user and django_user.pk:
            try:
                return cls.objects.get(django_user=django_user), False
            except cls.DoesNotExist:
                pass

        # 2. By email
        norm_email = (email or "").strip().lower() or None
        if norm_email:
            try:
                user = cls.objects.get(email=norm_email)
                cls._maybe_update(user, phone=phone, name=name, django_user=django_user)
                return user, False
            except cls.DoesNotExist:
                pass

        # 3. By phone (all candidates)
        norm_phone = cls._normalize_phone(phone)
        if norm_phone:
            candidates = cls._phone_candidates(phone)
            existing = cls.objects.filter(phone_number__in=candidates).first()
            if existing:
                cls._maybe_update(existing, email=norm_email, name=name, django_user=django_user)
                return existing, False

        # 4. Create — need at least a phone
        if not norm_phone:
            raise ValueError("phone ou email obrigatório para criar UnifiedUser")

        user = cls.objects.create(
            phone_number=norm_phone,
            email=norm_email,
            name=name or "Desconhecido",
            django_user=django_user,
        )
        return user, True

    @classmethod
    def _maybe_update(cls, user: "UnifiedUser", *, phone="", email="", name="", django_user=None):
        """Fills in missing fields without overwriting existing data."""
        updates = []
        if phone and not user.phone_number:
            user.phone_number = cls._normalize_phone(phone)
            updates.append("phone_number")
        if email and not user.email:
            user.email = email.strip().lower()
            updates.append("email")
        if name and not user.name:
            user.name = name
            updates.append("name")
        if django_user and not user.django_user_id:
            user.django_user = django_user
            updates.append("django_user")
        if updates:
            user.save(update_fields=updates)

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
