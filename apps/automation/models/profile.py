from django.db import models
from apps.core.models import BaseModel


class CompanyProfile(BaseModel):
    """
    Automation profile for a business.

    Store is the source of truth for business identity.
    CompanyProfile keeps automation settings and legacy compatibility fields.
    """

    class BusinessType(models.TextChoices):
        RESTAURANT = 'restaurant', 'Restaurante'
        ECOMMERCE = 'ecommerce', 'E-commerce'
        SERVICES = 'services', 'Servicos'
        RETAIL = 'retail', 'Varejo'
        HEALTHCARE = 'healthcare', 'Saude'
        EDUCATION = 'education', 'Educacao'
        OTHER = 'other', 'Outro'

    STORE_TYPE_TO_BUSINESS_TYPE = {
        'food': BusinessType.RESTAURANT,
        'retail': BusinessType.RETAIL,
        'services': BusinessType.SERVICES,
        'digital': BusinessType.ECOMMERCE,
        'other': BusinessType.OTHER,
    }

    account = models.OneToOneField(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='company_profile',
        null=True,
        blank=True
    )
    store = models.OneToOneField(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='automation_profile',
        null=True,
        blank=True
    )

    _company_name = models.CharField(max_length=255, db_column='company_name', blank=True)
    _business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.OTHER,
        db_column='business_type'
    )
    _description = models.TextField(blank=True, db_column='description')
    _legacy_whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
        default='',
        db_column='whatsapp_number',
        editable=False,
    )
    _legacy_address = models.TextField(
        blank=True,
        default='',
        db_column='address',
        editable=False,
    )

    website_url = models.URLField(blank=True)
    menu_url = models.URLField(blank=True, help_text='URL do cardapio/catalogo')
    order_url = models.URLField(blank=True, help_text='URL para fazer pedidos')
    _business_hours = models.JSONField(
        default=dict,
        blank=True,
        db_column='business_hours',
        help_text='DEPRECATED: Use store.operating_hours instead'
    )

    auto_reply_enabled = models.BooleanField(default=True)
    welcome_message_enabled = models.BooleanField(default=True)
    menu_auto_send = models.BooleanField(
        default=True,
        help_text='Enviar cardapio automaticamente na primeira mensagem'
    )

    abandoned_cart_notification = models.BooleanField(default=True)
    abandoned_cart_delay_minutes = models.PositiveIntegerField(
        default=30,
        help_text='Minutos para esperar antes de notificar carrinho abandonado'
    )
    pix_notification_enabled = models.BooleanField(default=True)
    payment_confirmation_enabled = models.BooleanField(default=True)
    order_status_notification_enabled = models.BooleanField(default=True)
    delivery_notification_enabled = models.BooleanField(default=True)

    external_api_key = models.CharField(
        max_length=255,
        blank=True,
        help_text='API key para o site externo se conectar'
    )
    webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text='Secret para validar webhooks do site'
    )

    use_ai_agent = models.BooleanField(
        default=False,
        help_text='Usar Agente IA (Langchain) para respostas avancadas'
    )
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_profiles',
        help_text='Agente IA padrao para respostas automaticas'
    )

    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text='Configuracoes personalizadas'
    )

    class Meta:
        app_label = 'automation'
        db_table = 'company_profiles'
        verbose_name = 'Company Profile'
        verbose_name_plural = 'Company Profiles'
        constraints = [
            models.CheckConstraint(
                check=models.Q(store__isnull=False) | models.Q(account__isnull=False),
                name='company_profile_requires_store_or_account',
            )
        ]

    def get_effective_store(self):
        if self.store_id:
            return self.store

        if self.account_id:
            stores_manager = getattr(self.account, 'stores', None)
            if stores_manager is not None:
                return stores_manager.filter(is_active=True).first() or stores_manager.first()

        return None

    def get_effective_account(self):
        store = self.get_effective_store()
        if store and getattr(store, 'whatsapp_account_id', None):
            return store.whatsapp_account
        return self.account

    def get_default_agent(self):
        if self.default_agent_id:
            return self.default_agent

        account = self.get_effective_account()
        if account and getattr(account, 'default_agent_id', None):
            return account.default_agent

        return None

    def is_ai_enabled(self) -> bool:
        return bool(self.use_ai_agent and self.get_default_agent())

    @property
    def company_name(self):
        store = self.get_effective_store()
        if store:
            return store.name
        return self._company_name

    @company_name.setter
    def company_name(self, value):
        self._company_name = value

    @property
    def business_type(self):
        store = self.get_effective_store()
        if store:
            return self.STORE_TYPE_TO_BUSINESS_TYPE.get(store.store_type, self.BusinessType.OTHER)
        return self._business_type

    @business_type.setter
    def business_type(self, value):
        self._business_type = value

    @property
    def description(self):
        store = self.get_effective_store()
        if store:
            return store.description or ''
        return self._description

    @description.setter
    def description(self, value):
        self._description = value

    @property
    def business_hours(self):
        store = self.get_effective_store()
        if store:
            return store.operating_hours or {}
        return self._business_hours or {}

    @business_hours.setter
    def business_hours(self, value):
        self._business_hours = value or {}

    @property
    def phone_number(self):
        store = self.get_effective_store()
        if store and (store.whatsapp_number or store.phone):
            return store.whatsapp_number or store.phone

        account = self.get_effective_account()
        if account:
            return account.phone_number

        return self._legacy_whatsapp_number

    @property
    def email(self):
        store = self.get_effective_store()
        return store.email if store else ''

    @property
    def address(self):
        store = self.get_effective_store()
        if store and store.address:
            return store.address
        return self._legacy_address

    @property
    def city(self):
        store = self.get_effective_store()
        return store.city if store else ''

    @property
    def state(self):
        store = self.get_effective_store()
        return store.state if store else ''

    @property
    def store_slug(self):
        store = self.get_effective_store()
        return store.slug if store else None

    def get_menu_url(self):
        if self.menu_url:
            return self.menu_url

        store = self.get_effective_store()
        if store and getattr(store, 'website_url', ''):
            return store.website_url.rstrip('/')

        return self.website_url or ''

    def get_order_url(self):
        if self.order_url:
            return self.order_url

        store = self.get_effective_store()
        if store and getattr(store, 'website_url', ''):
            return store.website_url.rstrip('/')

        return self.website_url or ''

    def sync_from_store(self, save: bool = True):
        store = self.get_effective_store()
        if not store:
            return

        update_fields = []

        if not self.store_id:
            self.store = store
            update_fields.append('store')

        if not self.account_id and store.whatsapp_account_id:
            self.account = store.whatsapp_account
            update_fields.append('account')

        if not self._company_name:
            self._company_name = store.name
            update_fields.append('_company_name')

        if not self._description and store.description:
            self._description = store.description
            update_fields.append('_description')

        if not self._legacy_whatsapp_number:
            self._legacy_whatsapp_number = store.whatsapp_number or store.phone or ''
            update_fields.append('_legacy_whatsapp_number')

        if not self._legacy_address and store.address:
            self._legacy_address = store.address
            update_fields.append('_legacy_address')

        if store.operating_hours and self._business_hours != store.operating_hours:
            self._business_hours = store.operating_hours
            update_fields.append('_business_hours')

        if not self.menu_url and getattr(store, 'website_url', ''):
            self.menu_url = store.website_url.rstrip('/')
            update_fields.append('menu_url')

        if not self.order_url and getattr(store, 'website_url', ''):
            self.order_url = store.website_url.rstrip('/')
            update_fields.append('order_url')

        if save and update_fields:
            self.save(update_fields=list(dict.fromkeys(update_fields + ['updated_at'])))

    def sync_ai_settings_to_account(self, save: bool = True):
        account = self.get_effective_account()
        if not account:
            return

        update_fields = []
        if account.default_agent_id != self.default_agent_id:
            account.default_agent_id = self.default_agent_id
            update_fields.append('default_agent')

        desired_auto_response = bool(self.use_ai_agent)
        if account.auto_response_enabled != desired_auto_response:
            account.auto_response_enabled = desired_auto_response
            update_fields.append('auto_response_enabled')

        if save and update_fields:
            account.save(update_fields=list(dict.fromkeys(update_fields + ['updated_at'])))

    def generate_api_key(self):
        """Generate a new API key for external integrations."""
        import secrets

        self.external_api_key = secrets.token_urlsafe(32)
        self.save(update_fields=['external_api_key', 'updated_at'])
        return self.external_api_key

    def generate_webhook_secret(self):
        """Generate a new webhook secret."""
        import secrets

        self.webhook_secret = secrets.token_urlsafe(32)
        self.save(update_fields=['webhook_secret', 'updated_at'])
        return self.webhook_secret

    def __str__(self):
        name = self.company_name or 'Unnamed'
        phone = self.phone_number or 'No WhatsApp'
        return f'{name} ({phone})'
