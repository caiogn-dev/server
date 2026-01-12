"""
Management command to set up Pastita as a Store in the unified system.
This creates the Store entity and links existing data.
"""
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreIntegration
from apps.ecommerce.models import DeliveryZone, Coupon

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
        if existing_store and not force:
            self.stdout.write(self.style.WARNING(
                f'Pastita store already exists (ID: {existing_store.id}). Use --force to recreate.'
            ))
            return

        if existing_store and force:
            self.stdout.write(self.style.WARNING('Deleting existing Pastita store...'))
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
            owner.set_password('pastita2024!')
            owner.save()
            self.stdout.write(self.style.SUCCESS(f'Created owner user: {owner_email}'))
        else:
            self.stdout.write(f'Using existing owner: {owner_email}')

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
            phone='(63) 99295-7931',
            whatsapp_number='5563992957931',
            
            # Address (Palmas, TO)
            address='Q. 112 Sul Rua SR 1, conj. 06 lote 04 - Plano Diretor Sul',
            city='Palmas',
            state='TO',
            zip_code='77020-170',
            country='BR',
            latitude=Decimal('-10.1847'),
            longitude=Decimal('-48.3337'),
            
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
            
            metadata={
                'legacy_app': 'pastita',
                'product_types': ['molho', 'carne', 'rondelli', 'combo'],
                'here_api_key': 'G9H9YAXgkVi1YDXhkea18Sb5EIUAch5m1oNYoaPUZNw',
            }
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

        # Create WhatsApp Integration
        wa_integration = StoreIntegration.objects.create(
            store=store,
            integration_type=StoreIntegration.IntegrationType.WHATSAPP,
            name='WhatsApp Business - Pastita',
            status=StoreIntegration.IntegrationStatus.PENDING,
            external_id='5563992957931',
            settings={
                'greeting_message': 'Olá! Bem-vindo à Pastita - Massas Artesanais! 🍝',
                'auto_reply': True,
            }
        )
        self.stdout.write(f'  Created WhatsApp integration')

        # Link existing delivery zones to Pastita
        updated_zones = DeliveryZone.objects.filter(store__isnull=True).update(store=store)
        self.stdout.write(f'  Linked {updated_zones} delivery zones to Pastita')

        # Link existing coupons to Pastita
        updated_coupons = Coupon.objects.filter(store__isnull=True).update(store=store)
        self.stdout.write(f'  Linked {updated_coupons} coupons to Pastita')

        # Create default delivery zones if none exist
        if not DeliveryZone.objects.filter(store=store).exists():
            default_zones = [
                {'name': 'Centro', 'distance_band': '0_2', 'delivery_fee': Decimal('5.00'), 'color': '#4CAF50', 'estimated_minutes': 15, 'sort_order': 1},
                {'name': 'Próximo', 'distance_band': '2_5', 'delivery_fee': Decimal('8.00'), 'color': '#8BC34A', 'estimated_minutes': 20, 'sort_order': 2},
                {'name': 'Médio', 'distance_band': '5_8', 'delivery_fee': Decimal('12.00'), 'color': '#FFC107', 'estimated_minutes': 25, 'sort_order': 3},
                {'name': 'Distante', 'distance_band': '8_12', 'delivery_fee': Decimal('15.00'), 'color': '#FF9800', 'estimated_minutes': 30, 'sort_order': 4},
                {'name': 'Muito Distante', 'distance_band': '12_15', 'delivery_fee': Decimal('20.00'), 'color': '#FF5722', 'estimated_minutes': 40, 'sort_order': 5},
                {'name': 'Área Estendida', 'distance_band': '15_20', 'delivery_fee': Decimal('25.00'), 'color': '#E91E63', 'estimated_minutes': 50, 'sort_order': 6},
            ]
            for zone_data in default_zones:
                DeliveryZone.objects.create(
                    store=store,
                    zone_type='distance_band',
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
