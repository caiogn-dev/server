from django.db import models
from apps.core.models import BaseModel


class CustomerSession(BaseModel):
    """
    Track customer session between website and WhatsApp.
    Links cart, orders, and payments to a customer.
    """

    class SessionStatus(models.TextChoices):
        ACTIVE = 'active', 'Ativa'
        CART_CREATED = 'cart_created', 'Carrinho Criado'
        CART_ABANDONED = 'cart_abandoned', 'Carrinho Abandonado'
        CHECKOUT = 'checkout', 'Em Checkout'
        PAYMENT_PENDING = 'payment_pending', 'Aguardando Pagamento'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
        ORDER_PLACED = 'order_placed', 'Pedido Realizado'
        COMPLETED = 'completed', 'Concluída'
        EXPIRED = 'expired', 'Expirada'

    company = models.ForeignKey(
        'automation.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='customer_sessions'
    )

    phone_number = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    unified_user = models.ForeignKey(
        'users.UnifiedUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_sessions',
    )

    session_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="ID da sessão no site externo"
    )
    external_customer_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID do cliente no site externo"
    )

    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE
    )

    cart_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dados do carrinho"
    )
    cart_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    cart_items_count = models.PositiveIntegerField(default=0)
    cart_created_at = models.DateTimeField(null=True, blank=True)
    cart_updated_at = models.DateTimeField(null=True, blank=True)

    # DEPRECATED: PIX é fonte de verdade em StoreOrder.pix_code — manter enquanto migração em andamento
    pix_code = models.TextField(blank=True)
    # DEPRECATED: PIX é fonte de verdade em StoreOrder.pix_qr_code — manter enquanto migração em andamento
    pix_qr_code = models.TextField(blank=True)
    # DEPRECATED: PIX é fonte de verdade em StoreOrder.pix_expires_at — manter enquanto migração em andamento
    pix_expires_at = models.DateTimeField(null=True, blank=True)
    payment_id = models.CharField(max_length=100, blank=True)

    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_sessions'
    )
    external_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID do pedido no site externo"
    )

    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_sessions'
    )

    delivery_method = models.CharField(
        max_length=20,
        default='delivery',
        help_text="Método de entrega: 'delivery' ou 'pickup'"
    )
    delivery_address = models.TextField(
        blank=True,
        default='',
        help_text="Endereço de entrega"
    )
    payment_method = models.CharField(
        max_length=20,
        default='pix',
        help_text="Método de pagamento: 'pix', 'card', 'cash'"
    )

    notifications_sent = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de notificações enviadas"
    )
    last_notification_at = models.DateTimeField(null=True, blank=True)

    last_activity_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Memória curta do bot ("acabei de oferecer o Camarão", "montando o combo
    # X") dentro do próprio cart_data — sem coluna nova. Até 06/10 três
    # recursos chamavam `session.context`/`update_context` que só existiam na
    # sessão de FLUXO: o produto oferecido nunca era lembrado, a montagem de
    # combo nunca começava, e o erro era engolido em silêncio.
    _CHAVE_CONTEXTO = 'contexto'

    @property
    def context(self) -> dict:
        return dict((self.cart_data or {}).get(self._CHAVE_CONTEXTO) or {})

    def update_context(self, key: str, value) -> None:
        """Grava uma chave do contexto relendo o cart_data antes (não pisa no carrinho)."""
        if self.pk:
            self.refresh_from_db(fields=['cart_data'])
        dados = dict(self.cart_data or {})
        contexto = dict(dados.get(self._CHAVE_CONTEXTO) or {})
        if value is None:
            contexto.pop(key, None)
        else:
            contexto[key] = value
        dados[self._CHAVE_CONTEXTO] = contexto
        self.cart_data = dados
        self.save(update_fields=['cart_data'])

    class Meta:
        app_label = 'automation'
        db_table = 'customer_sessions'
        verbose_name = 'Customer Session'
        verbose_name_plural = 'Customer Sessions'
        ordering = ['-last_activity_at']
        indexes = [
            models.Index(fields=['company', 'phone_number', '-created_at']),
            models.Index(fields=['session_id']),
            models.Index(fields=['status', '-last_activity_at']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.status} ({self.company.company_name})"

    def add_notification(self, notification_type: str):
        """Record that a notification was sent."""
        from django.utils import timezone
        self.notifications_sent.append({
            'type': notification_type,
            'sent_at': timezone.now().isoformat()
        })
        self.last_notification_at = timezone.now()
        self.save(update_fields=['notifications_sent', 'last_notification_at'])

    def was_notification_sent(self, notification_type: str) -> bool:
        """Check if a notification type was already sent."""
        return any(n['type'] == notification_type for n in self.notifications_sent)
