"""
Management command to setup Mercado Pago webhook integration.
Usage:
    python manage.py setup_mercadopago_webhook --store pastita --api-key YOUR_API_KEY --webhook-secret YOUR_SECRET
"""
from django.core.management.base import BaseCommand, CommandError
from apps.stores.models import Store, StoreIntegration


class Command(BaseCommand):
    help = 'Setup Mercado Pago webhook integration for a store'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store',
            type=str,
            required=True,
            help='Store slug (e.g., pastita)'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            required=True,
            help='Mercado Pago API Key (Access Token)'
        )
        parser.add_argument(
            '--webhook-secret',
            type=str,
            required=True,
            help='Mercado Pago Webhook Secret (assinatura)'
        )
        parser.add_argument(
            '--public-key',
            type=str,
            default='',
            help='Mercado Pago Public Key (optional)'
        )
        parser.add_argument(
            '--name',
            type=str,
            default='Mercado Pago',
            help='Integration display name'
        )

    def handle(self, *args, **options):
        store_slug = options['store']
        api_key = options['api_key']
        webhook_secret = options['webhook_secret']
        public_key = options['public_key']
        name = options['name']

        # Get store
        try:
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            raise CommandError(f'Store with slug "{store_slug}" does not exist')

        self.stdout.write(f'Configuring Mercado Pago for store: {store.name}')

        # Create or update integration
        integration, created = StoreIntegration.objects.update_or_create(
            store=store,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            defaults={
                'name': name,
                'status': StoreIntegration.IntegrationStatus.ACTIVE,
                'access_token': api_key,  # Mercado Pago Access Token
                'api_key': public_key,     # Public Key (if needed)
                'webhook_secret': webhook_secret,
                'settings': {
                    'public_key': public_key,
                    'webhook_url': f'/webhooks/payments/mercadopago/',
                    'ipn_url': f'/webhooks/payments/mercadopago/',
                }
            }
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{action} Mercado Pago integration for {store.name}\n'
                f'  - API Key: {api_key[:10]}...{api_key[-4:]}\n'
                f'  - Webhook Secret: {webhook_secret[:10]}...{webhook_secret[-4:]}\n'
                f'  - Webhook URL: /webhooks/payments/mercadopago/{store_slug}/\n'
                f'\nConfigure no Mercado Pago:\n'
                f'  1. Acesse: https://www.mercadopago.com.br/developers/panel/app\n'
                f'  2. Webhooks > Configurar webhook\n'
                f'  3. URL: https://seu-dominio.com/webhooks/payments/mercadopago/{store_slug}/\n'
                f'  4. Events: payment, merchant_order\n'
                f'  5. Secret: {webhook_secret}'
            )
        )