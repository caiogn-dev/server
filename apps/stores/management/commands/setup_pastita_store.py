"""
Management command to set up Pastita as a Store in the unified system.
This creates the Store entity and links existing data.
"""
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.conf import settings

from apps.stores.models import Store, StoreCategory, StoreIntegration, StoreDeliveryZone, StoreCoupon
from apps.whatsapp.utils import get_default_whatsapp_account

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Set up Pastita as a Store in the unified multi-store system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--owner-email',
            type=str,
            default='admin@pastita.com.br',
            help='Email of the store owner (will be created if not exists)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation even if store exists'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        owner_email = options['owner_email']
        force = options['force']

        self.stdout.write(self.style.NOTICE('Setting up Pastita Store...'))

        # Check if store already exists
        existing_store = Store.objects.filter(slug='pastita').first()
        if existing_store:
            self.ensure_whatsapp_integration(existing_store)
            if not force:
                self.stdout.write(self.style.WARNING(
                    f'Pastita store already exists (ID: {existing_store.id}). Use --force to recreate.'
                ))
                return
            self.stdout.write(self.style.WARNING('Deleting existing Pastita store...'))
            self._cleanup_legacy_ecommerce_rows(existing_store.id)
            existing_store.delete()

        # Get or create owner
        owner, created = User.objects.get_or_create(
            email=owner_email,
            defaults={
                'username': 'pastita_admin',
                'first_name': 'Pastita',
                'last_name': 'Admin',
                'is_staff': True,
            }
        )
        if created:
            # Get password from environment or generate a random secure one
            import secrets
            import os
            password = os.environ.get('PASTITA_OWNER_PASSWORD', secrets.token_urlsafe(16))
            owner.set_password(password)
            owner.save()
            self.stdout.write(self.style.SUCCESS(f'Created owner user: {owner_email}'))
            if 'PASTITA_OWNER_PASSWORD' not in os.environ:
                self.stdout.write(self.style.WARNING(f'Generated password (save this!): {password}'))
        else:
            self.stdout.write(f'Using existing owner: {owner_email}')

        here_api_key = getattr(settings, 'HERE_API_KEY', '').strip()
        pastita_whatsapp_number = getattr(settings, 'PASTITA_WHATSAPP_NUMBER', '').strip()
        store_metadata = {
            'legacy_app': 'pastita',
            'product_types': ['molho', 'carne', 'rondelli', 'combo'],
        }
        if here_api_key:
            store_metadata['here_api_key'] = here_api_key

        # Create Pastita Store
        store = Store.objects.create(
            name='Pastita - Massas Artesanais',
            slug='pastita',
            description='Massas artesanais premium feitas com ingredientes selecionados. '
                       'Rondellis, molhos especiais e carnes de qualidade.',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            
            # Contact
            email='contato@pastita.com.br',
            phone='(63) 9117-2166',
            whatsapp_number=pastita_whatsapp_number,
            
            # Address (Palmas, TO) - Ivoneth Banqueteria
            address='Q. 112 Sul Rua SR 1, conj. 06 lote 04 - Plano Diretor Sul',
            city='Palmas',
            state='TO',
            zip_code='77020-170',
            country='BR',
            latitude=Decimal('-10.185260'),
            longitude=Decimal('-48.303478'),
            
            # Branding
            primary_color='#722F37',  # Marsala
            secondary_color='#D4AF37',  # Gold
            
            # Business Settings
            currency='BRL',
            timezone='America/Sao_Paulo',
            
            # Delivery Settings
            delivery_enabled=True,
            pickup_enabled=True,
            min_order_value=Decimal('30.00'),
            free_delivery_threshold=Decimal('100.00'),
            default_delivery_fee=Decimal('8.00'),
            
            # Operating Hours
            operating_hours={
                'monday': {'open': '11:00', 'close': '22:00'},
                'tuesday': {'open': '11:00', 'close': '22:00'},
                'wednesday': {'open': '11:00', 'close': '22:00'},
                'thursday': {'open': '11:00', 'close': '22:00'},
                'friday': {'open': '11:00', 'close': '23:00'},
                'saturday': {'open': '11:00', 'close': '23:00'},
                'sunday': {'open': '11:00', 'close': '21:00'},
            },
            
            owner=owner,
            
            metadata=store_metadata
        )
        self.stdout.write(self.style.SUCCESS(f'Created Pastita store (ID: {store.id})'))

        # Create Product Categories
        categories_data = [
            {
                'name': 'Molhos',
                'slug': 'molhos',
                'description': 'Molhos artesanais para acompanhar suas massas',
                'sort_order': 1,
                'metadata': {
                    'product_model': 'Molho',
                    'fields': ['tipo', 'quantidade'],
                    'tipo_choices': [
                        ('4queijos', '4 Queijos'),
                        ('sugo', 'Sugo'),
                        ('branco', 'Molho Branco'),
                        ('pesto', 'Pesto'),
                        ('bolonhesa', 'Bolonhesa'),
                        ('carbonara', 'Carbonara'),
                    ]
                }
            },
            {
                'name': 'Carnes',
                'slug': 'carnes',
                'description': 'Proteínas selecionadas para complementar sua refeição',
                'sort_order': 2,
                'metadata': {
                    'product_model': 'Carne',
                    'fields': ['tipo', 'quantidade', 'molhos'],
                    'tipo_choices': [
                        ('isca_file', 'Iscas de Filé'),
                        ('frango_grelhado', 'Frango Grelhado'),
                        ('carne_moida', 'Carne Moída'),
                        ('linguica_calabresa', 'Linguiça Calabresa'),
                        ('bacon', 'Bacon'),
                        ('costela', 'Costela Desfiada'),
                        ('picanha', 'Picanha'),
                    ]
                }
            },
            {
                'name': 'Rondellis Clássicos',
                'slug': 'rondellis-classicos',
                'description': 'Nossos rondellis tradicionais com recheios clássicos',
                'sort_order': 3,
                'metadata': {
                    'product_model': 'Rondelli',
                    'categoria': 'classicos',
                    'fields': ['sabor', 'categoria'],
                }
            },
            {
                'name': 'Rondellis Gourmet',
                'slug': 'rondellis-gourmet',
                'description': 'Rondellis especiais com recheios premium',
                'sort_order': 4,
                'metadata': {
                    'product_model': 'Rondelli',
                    'categoria': 'gourmet',
                    'fields': ['sabor', 'categoria'],
                }
            },
            {
                'name': 'Combos',
                'slug': 'combos',
                'description': 'Combinações especiais com preço promocional',
                'sort_order': 5,
                'metadata': {
                    'product_model': 'Combo',
                    'fields': ['itens'],
                }
            },
        ]

        for cat_data in categories_data:
            metadata = cat_data.pop('metadata', {})
            category = StoreCategory.objects.create(
                store=store,
                **cat_data
            )
            # Store metadata in a separate field if needed
            self.stdout.write(f'  Created category: {category.name}')

        # Create Mercado Pago Integration
        mp_integration = StoreIntegration.objects.create(
            store=store,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            name='Mercado Pago - Pastita',
            status=StoreIntegration.IntegrationStatus.ACTIVE,
            settings={
                'sandbox': False,
                'payment_methods': ['pix', 'credit_card', 'debit_card'],
                'notification_url': '/webhooks/payments/mercadopago/',
            },
            metadata={
                'note': 'Access token should be set via admin or API'
            }
        )
        self.stdout.write(f'  Created Mercado Pago integration')

        self.ensure_whatsapp_integration(store)

        # Create default coupons if none exist (using StoreCoupon)
        if not StoreCoupon.objects.filter(store=store).exists():
            from django.utils import timezone
            default_coupons = [
                {
                    'code': 'BEMVINDO10',
                    'description': '10% de desconto na primeira compra',
                    'discount_type': 'percentage',
                    'discount_value': Decimal('10.00'),
                    'min_purchase': Decimal('50.00'),
                    'first_order_only': True,
                    'valid_from': timezone.now(),
                    'valid_until': timezone.now() + timezone.timedelta(days=365),
                },
                {
                    'code': 'FRETEGRATIS',
                    'description': 'Frete grátis em compras acima de R$ 100',
                    'discount_type': 'fixed',
                    'discount_value': Decimal('15.00'),
                    'min_purchase': Decimal('100.00'),
                    'valid_from': timezone.now(),
                    'valid_until': timezone.now() + timezone.timedelta(days=365),
                },
            ]
            for coupon_data in default_coupons:
                StoreCoupon.objects.create(store=store, **coupon_data)
            self.stdout.write(f'  Created {len(default_coupons)} default coupons')

        # Create default delivery zones if none exist (using StoreDeliveryZone)
        if not StoreDeliveryZone.objects.filter(store=store).exists():
            default_zones = [
                {'name': 'Centro', 'distance_band': '0_2', 'delivery_fee': Decimal('5.00'), 'color': '#4CAF50', 'estimated_minutes': 15, 'sort_order': 1},
                {'name': 'Próximo', 'distance_band': '2_5', 'delivery_fee': Decimal('8.00'), 'color': '#8BC34A', 'estimated_minutes': 20, 'sort_order': 2},
                {'name': 'Médio', 'distance_band': '5_8', 'delivery_fee': Decimal('12.00'), 'color': '#FFC107', 'estimated_minutes': 25, 'sort_order': 3},
                {'name': 'Distante', 'distance_band': '8_12', 'delivery_fee': Decimal('15.00'), 'color': '#FF9800', 'estimated_minutes': 30, 'sort_order': 4},
                {'name': 'Muito Distante', 'distance_band': '12_15', 'delivery_fee': Decimal('20.00'), 'color': '#FF5722', 'estimated_minutes': 40, 'sort_order': 5},
                {'name': 'Área Estendida', 'distance_band': '15_20', 'delivery_fee': Decimal('25.00'), 'color': '#E91E63', 'estimated_minutes': 50, 'sort_order': 6},
            ]
            for zone_data in default_zones:
                StoreDeliveryZone.objects.create(
                    store=store,
                    zone_type='distance_band',
                    estimated_days=0,
                    **zone_data
                )
            self.stdout.write(f'  Created {len(default_zones)} default delivery zones')

        self.stdout.write(self.style.SUCCESS('\n✅ Pastita store setup complete!'))
        self.stdout.write(f'\nStore Details:')
        self.stdout.write(f'  ID: {store.id}')
        self.stdout.write(f'  Slug: {store.slug}')
        self.stdout.write(f'  Owner: {owner.email}')
        self.stdout.write(f'  Categories: {store.categories.count()}')
        self.stdout.write(f'  Integrations: {store.integrations.count()}')
        self.stdout.write(f'  Delivery Zones: {store.delivery_zones.count()}')

    def ensure_whatsapp_integration(self, store):
        """
        Ensure the store has a WhatsApp integration and link it to the default account when available.
        """
        account = get_default_whatsapp_account(create_if_missing=False)
        status = StoreIntegration.IntegrationStatus.ACTIVE if account else StoreIntegration.IntegrationStatus.PENDING

        defaults = {
            'name': 'WhatsApp Business - Pastita',
            'status': status,
            'settings': {'auto_reply': True, 'auto_linked': bool(account)},
            'metadata': {'auto_linked': bool(account)},
        }

        if account:
            defaults.update({
                'external_id': str(account.id),
                'phone_number_id': account.phone_number_id or '',
                'waba_id': account.waba_id or '',
            })

        integration, created = StoreIntegration.objects.get_or_create(
            store=store,
            integration_type=StoreIntegration.IntegrationType.WHATSAPP,
            defaults=defaults
        )

        if account and not created:
            updated_fields = []
            if integration.external_id != str(account.id):
                integration.external_id = str(account.id)
                updated_fields.append('external_id')
            if account.phone_number_id and integration.phone_number_id != account.phone_number_id:
                integration.phone_number_id = account.phone_number_id
                updated_fields.append('phone_number_id')
            if account.waba_id and integration.waba_id != account.waba_id:
                integration.waba_id = account.waba_id
                updated_fields.append('waba_id')
            if integration.status != StoreIntegration.IntegrationStatus.ACTIVE:
                integration.status = StoreIntegration.IntegrationStatus.ACTIVE
                updated_fields.append('status')

            settings_meta = integration.settings or {}
            if settings_meta.get('auto_linked') is not True:
                settings_meta['auto_linked'] = True
                integration.settings = settings_meta
                updated_fields.append('settings')

            metadata_key = getattr(settings, 'DEFAULT_WHATSAPP_STORE_METADATA_KEY', 'whatsapp_account_id')
            metadata_value = integration.metadata or {}
            if metadata_value.get('auto_linked') is not True:
                metadata_value['auto_linked'] = True
                integration.metadata = metadata_value
                updated_fields.append('metadata')

            if updated_fields:
                integration.save(update_fields=updated_fields + ['updated_at'])

        metadata_key = getattr(settings, 'DEFAULT_WHATSAPP_STORE_METADATA_KEY', 'whatsapp_account_id')
        metadata = store.metadata or {}
        desired_account_id = str(account.id) if account else ''
        if desired_account_id:
            if metadata.get(metadata_key) != desired_account_id:
                metadata[metadata_key] = desired_account_id
                store.metadata = metadata
                store.save(update_fields=['metadata'])
        else:
            self.stdout.write('  WhatsApp integration remains pending because the default account is not configured.')

    def _cleanup_legacy_ecommerce_rows(self, store_id):
        """Delete rows from the legacy ecommerce tables that reference stores."""
        cleanup_statements = [
            "DELETE FROM ecommerce_coupon WHERE store_id = %s",
            "DELETE FROM ecommerce_deliveryzone WHERE store_id = %s",
        ]

        try:
            with connection.cursor() as cursor:
                for stmt in cleanup_statements:
                    cursor.execute(stmt, [str(store_id)])
        except Exception:
            pass
