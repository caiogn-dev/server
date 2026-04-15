from django import forms
from django.conf import settings
from django.contrib import admin

from .services.checkout_service import CheckoutService
from .models import (
    Store, StoreIntegration, StoreWebhook, StoreCategory,
    StoreProduct, StoreProductVariant, StoreOrder, StoreOrderItem,
    StoreCustomer,
    StorePaymentGateway, StorePayment, StorePaymentWebhookEvent,
)


def _strip_trailing_slash(url):
    return (url or '').rstrip('/')


def _build_default_mp_webhook_url(store):
    if not store:
        return ''
    base_url = _strip_trailing_slash(getattr(settings, 'BASE_URL', ''))
    if not base_url:
        return ''
    return f"{base_url}/api/v1/stores/{store.slug}/webhooks/mercadopago/"


def _resolve_integration_webhook_url(integration):
    if not integration or not integration.store_id:
        return ''

    configured_url = (
        integration.webhook_url
        or (integration.settings or {}).get('notification_url')
        or (integration.settings or {}).get('webhook_url')
    )
    if configured_url:
        if configured_url.startswith(('http://', 'https://')):
            return _strip_trailing_slash(configured_url)
        base_url = _strip_trailing_slash(getattr(settings, 'BASE_URL', ''))
        if base_url:
            return f"{base_url}/{configured_url.lstrip('/')}"
        return configured_url

    return _build_default_mp_webhook_url(integration.store)


class StoreAdminForm(forms.ModelForm):
    frontend_url = forms.URLField(
        required=False,
        label='Frontend URL',
        help_text='URL publica da loja usada nos retornos do checkout. Se ficar em branco, o backend usa FRONTEND_URL global.',
    )

    class Meta:
        model = Store
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        metadata = dict(self.instance.metadata or {}) if self.instance and self.instance.pk else {}
        self.fields['frontend_url'].initial = (
            metadata.get('frontend_url')
            or metadata.get('site_url')
            or metadata.get('website_url')
            or ''
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.operating_hours is None:
            instance.operating_hours = {}
        if instance.metadata is None:
            instance.metadata = {}
        metadata = dict(instance.metadata or {})
        frontend_url = (self.cleaned_data.get('frontend_url') or '').strip()

        if frontend_url:
            metadata['frontend_url'] = frontend_url
        else:
            metadata.pop('frontend_url', None)

        instance.metadata = metadata

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StoreIntegrationAdminForm(forms.ModelForm):
    public_key = forms.CharField(
        required=False,
        label='Public key',
        help_text='Chave publica do app do Mercado Pago usada pelo checkout no frontend.',
    )
    access_token = forms.CharField(
        required=False,
        label='Access token',
        strip=False,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
        help_text='Token privado usado pelo backend para criar pagamentos.',
    )
    webhook_secret = forms.CharField(
        required=False,
        label='Webhook secret',
        strip=False,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
        help_text='Assinatura secreta enviada pelo painel do Mercado Pago para validar webhooks.',
    )
    webhook_verify_token = forms.CharField(
        required=False,
        label='Webhook verify token',
        help_text='Opcional. Use apenas se a integracao exigir token de verificacao adicional.',
    )
    sandbox = forms.BooleanField(
        required=False,
        label='Sandbox',
        help_text='Marque apenas quando esta integracao deve operar em modo teste.',
    )

    class Meta:
        model = StoreIntegration
        exclude = ['api_key_encrypted', 'api_secret_encrypted', 'access_token_encrypted', 'refresh_token_encrypted']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['public_key'].initial = self.instance.api_key
            self.fields['access_token'].initial = self.instance.access_token
            self.fields['sandbox'].initial = bool((self.instance.settings or {}).get('sandbox', False))

        store = None
        if self.instance and self.instance.store_id:
            store = self.instance.store

        default_webhook_url = _build_default_mp_webhook_url(store)
        if default_webhook_url:
            self.fields['webhook_url'].widget.attrs.setdefault('placeholder', default_webhook_url)
            self.fields['webhook_url'].help_text = (
                f"Se ficar em branco, o backend usa automaticamente {default_webhook_url}"
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.metadata is None:
            instance.metadata = {}
        if instance.settings is None:
            instance.settings = {}
        integration_settings = dict(instance.settings or {})

        public_key = (self.cleaned_data.get('public_key') or '').strip()
        access_token = self.cleaned_data.get('access_token') or ''
        webhook_url = (self.cleaned_data.get('webhook_url') or '').strip()

        instance.api_key = public_key
        instance.access_token = access_token

        if public_key:
            integration_settings['public_key'] = public_key
        else:
            integration_settings.pop('public_key', None)

        integration_settings['sandbox'] = bool(self.cleaned_data.get('sandbox'))

        if webhook_url:
            integration_settings['webhook_url'] = webhook_url
            integration_settings['notification_url'] = webhook_url
        else:
            integration_settings.pop('webhook_url', None)
            integration_settings.pop('notification_url', None)

        instance.settings = integration_settings

        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    form = StoreAdminForm
    list_display = ['name', 'slug', 'store_type', 'status', 'owner', 'checkout_frontend_url', 'created_at']
    list_filter = ['store_type', 'status', 'created_at']
    search_fields = ['name', 'slug', 'email']
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ['staff']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Loja', {
            'fields': (
                'name', 'slug', 'description', 'store_type', 'status', 'is_active',
                'owner', 'staff',
            )
        }),
        ('Checkout e Contato', {
            'fields': (
                'frontend_url', 'email', 'phone', 'whatsapp_number', 'whatsapp_account',
            )
        }),
        ('Branding', {
            'fields': (
                'logo', 'logo_url', 'banner', 'banner_url',
                'primary_color', 'secondary_color',
            )
        }),
        ('Endereco', {
            'fields': (
                'address', 'city', 'state', 'zip_code', 'country',
                'latitude', 'longitude',
            )
        }),
        ('Operacao', {
            'fields': (
                'currency', 'timezone', 'tax_rate',
                'delivery_enabled', 'pickup_enabled',
                'min_order_value', 'free_delivery_threshold', 'default_delivery_fee',
                'operating_hours',
            )
        }),
        ('Avancado', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Frontend checkout')
    def checkout_frontend_url(self, obj):
        return CheckoutService.get_store_frontend_url(obj) or '-'


@admin.register(StoreIntegration)
class StoreIntegrationAdmin(admin.ModelAdmin):
    form = StoreIntegrationAdminForm
    list_display = [
        'store', 'integration_type', 'name', 'status',
        'masked_public_key', 'masked_access_token', 'created_at',
    ]
    list_filter = ['integration_type', 'status']
    search_fields = ['store__name', 'name']
    raw_id_fields = ['store']
    readonly_fields = [
        'id', 'created_at', 'updated_at',
        'masked_public_key', 'masked_access_token',
        'resolved_webhook_url', 'last_error', 'last_error_at',
    ]
    fieldsets = (
        ('Integracao', {
            'fields': (
                'store', 'integration_type', 'name', 'status', 'is_active',
            )
        }),
        ('Mercado Pago', {
            'fields': (
                'public_key', 'access_token', 'sandbox',
                'webhook_secret', 'webhook_verify_token',
                'webhook_url', 'resolved_webhook_url',
            ),
            'description': 'Preencha aqui os dados do app da loja no Mercado Pago. O webhook resolvido abaixo e a URL esperada para o painel.',
        }),
        ('Conferencia', {
            'fields': ('masked_public_key', 'masked_access_token'),
            'classes': ('collapse',),
        }),
        ('Identificadores externos', {
            'fields': ('external_id', 'phone_number_id', 'waba_id', 'token_expires_at'),
            'classes': ('collapse',),
        }),
        ('Avancado', {
            'fields': ('settings', 'metadata'),
            'classes': ('collapse',),
        }),
        ('Monitoramento', {
            'fields': ('last_error', 'last_error_at'),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Public key salva')
    def masked_public_key(self, obj):
        return obj.masked_api_key or '-'

    @admin.display(description='Access token salvo')
    def masked_access_token(self, obj):
        return obj.masked_access_token or '-'

    @admin.display(description='Webhook resolvido')
    def resolved_webhook_url(self, obj):
        return _resolve_integration_webhook_url(obj) or '-'


@admin.register(StoreWebhook)
class StoreWebhookAdmin(admin.ModelAdmin):
    list_display = ['store', 'name', 'url', 'is_active', 'total_calls', 'successful_calls']
    list_filter = ['is_active', 'store']
    search_fields = ['store__name', 'name', 'url']


@admin.register(StoreCategory)
class StoreCategoryAdmin(admin.ModelAdmin):
    list_display = ['store', 'name', 'slug', 'parent', 'is_active', 'sort_order']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'store__name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreProduct)
class StoreProductAdmin(admin.ModelAdmin):
    list_display = ['store', 'name', 'sku', 'price', 'stock_quantity', 'status']
    list_filter = ['store', 'status', 'category']
    search_fields = ['name', 'sku', 'store__name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StoreProductVariant)
class StoreProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'name', 'sku', 'price', 'stock_quantity', 'is_active']
    list_filter = ['is_active', 'product__store']
    search_fields = ['name', 'sku', 'product__name']


@admin.register(StoreOrder)
class StoreOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'store', 'customer_name', 'status', 'payment_status', 'total', 'created_at']
    list_filter = ['store', 'status', 'payment_status', 'delivery_method']
    search_fields = ['order_number', 'customer_name', 'customer_email', 'customer_phone']
    readonly_fields = ['order_number']


@admin.register(StoreOrderItem)
class StoreOrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product_name', 'quantity', 'unit_price', 'subtotal']
    list_filter = ['order__store']
    search_fields = ['product_name', 'order__order_number']


@admin.register(StoreCustomer)
class StoreCustomerAdmin(admin.ModelAdmin):
    list_display = ['store', 'user', 'phone', 'total_orders', 'total_spent', 'created_at']
    list_filter = ['store', 'accepts_marketing']
    search_fields = ['user__email', 'phone', 'whatsapp']


@admin.register(StorePaymentGateway)
class StorePaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'gateway_type', 'is_enabled', 'is_default', 'is_sandbox', 'created_at']
    list_filter = ['gateway_type', 'is_enabled', 'is_default', 'is_sandbox', 'store']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(StorePayment)
class StorePaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_id', 'order', 'gateway', 'status', 'amount', 'currency', 'created_at']
    list_filter = ['status', 'payment_method', 'gateway__gateway_type', 'created_at']
    search_fields = ['payment_id', 'external_id', 'order__order_number', 'payer_email', 'payer_name']
    readonly_fields = ['payment_id', 'created_at', 'updated_at', 'paid_at']
    date_hierarchy = 'created_at'


@admin.register(StorePaymentWebhookEvent)
class StorePaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'gateway', 'processing_status', 'created_at']
    list_filter = ['processing_status', 'event_type', 'gateway__gateway_type', 'created_at']
    search_fields = ['event_id', 'event_type']
    readonly_fields = ['event_id', 'payload', 'headers', 'created_at', 'processed_at']
    date_hierarchy = 'created_at'
