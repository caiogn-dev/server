"""
Management command to populate delivery zones for all stores.

Usage:
    python manage.py populate_delivery_zones
"""
from decimal import Decimal
from django.core.management.base import BaseCommand

from apps.stores.models import Store, StoreDeliveryZone


PLANO_DIRETOR_ZONES = [
    {"name": "0 a 2 km", "min_distance": 0, "max_distance": 2, "base_fee": 7.00},
    {"name": "2,1 a 3 km", "min_distance": 2.1, "max_distance": 3, "base_fee": 8.00},
    {"name": "3,1 a 5 km", "min_distance": 3.1, "max_distance": 5, "base_fee": 9.00},
    {"name": "5,1 a 6 km", "min_distance": 5.1, "max_distance": 6, "base_fee": 10.00},
    {"name": "6,1 a 6,9 km", "min_distance": 6.1, "max_distance": 6.9, "base_fee": 11.00},
    {"name": "7 a 7,9 km", "min_distance": 7, "max_distance": 7.9, "base_fee": 12.00},
    {"name": "8 km", "min_distance": 8, "max_distance": 8, "base_fee": 13.00},
    {"name": "9 km", "min_distance": 9, "max_distance": 9, "base_fee": 14.00},
    {"name": "10 km", "min_distance": 10, "max_distance": 10, "base_fee": 15.00},
    {"name": "11 km", "min_distance": 11, "max_distance": 11, "base_fee": 16.00},
    {"name": "12 km", "min_distance": 12, "max_distance": 12, "base_fee": 18.00},
    {"name": "13 km", "min_distance": 13, "max_distance": 13, "base_fee": 20.00},
    {"name": "14 km", "min_distance": 14, "max_distance": 14, "base_fee": 22.00},
    {"name": "15 km", "min_distance": 15, "max_distance": 15, "base_fee": 24.00},
    {"name": "16 km", "min_distance": 16, "max_distance": 16, "base_fee": 26.00},
    {"name": "17 km", "min_distance": 17, "max_distance": 17, "base_fee": 28.00},
]

OUTRAS_LOCALIDADES = [
    {"name": "Bertha Ville, Irmã Dulce, União Sul", "base_fee": 30.00},
    {"name": "Aurenys 1, 2, 3 e 4, Setor Universitário", "base_fee": 37.00},
    {"name": "Taquaralto (Lago Sul, Morada, Santa Fé, etc)", "base_fee": 40.00},
    {"name": "Taquari, Flamboyant, Recanto das Araras", "base_fee": 45.00},
    {"name": "Aeroporto", "base_fee": 50.00},
    {"name": "Luzimangues", "base_fee": 50.00},
    {"name": "Setor Água Fria (sentido Polinésia)", "base_fee": 25.00},
]


class Command(BaseCommand):
    help = 'Populate delivery zones for all stores.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing zones and recreate.',
        )

    def handle(self, *args, **options):
        force = options['force']

        self.stdout.write(self.style.NOTICE('\n' + '=' * 60))
        self.stdout.write(self.style.NOTICE('POPULANDO ZONAS DE ENTREGA'))
        self.stdout.write(self.style.NOTICE('=' * 60 + '\n'))

        stores = Store.objects.filter(slug__in=['kero-kero', 'ce-saladas', 'pastita'])

        if force:
            StoreDeliveryZone.objects.filter(store__in=stores).delete()
            self.stdout.write('  🗑️  Zonas antigas deletadas\n')

        for store in stores:
            self.stdout.write(f'📍 {store.name}')

            plano_count = 0
            for zone_data in PLANO_DIRETOR_ZONES:
                StoreDeliveryZone.objects.get_or_create(
                    store=store,
                    name=zone_data['name'],
                    zone_type='distance_band',
                    defaults={
                        'min_km': Decimal(str(zone_data['min_distance'])),
                        'max_km': Decimal(str(zone_data['max_distance'])),
                        'delivery_fee': Decimal(str(zone_data['base_fee'])),
                        'is_active': True,
                    }
                )
                plano_count += 1

            localidade_count = 0
            for zone_data in OUTRAS_LOCALIDADES:
                StoreDeliveryZone.objects.get_or_create(
                    store=store,
                    name=zone_data['name'],
                    zone_type='distance_band',
                    defaults={
                        'delivery_fee': Decimal(str(zone_data['base_fee'])),
                        'is_active': True,
                    }
                )
                localidade_count += 1

            self.stdout.write(f'  ✅ {plano_count} zonas Plano Diretor')
            self.stdout.write(f'  ✅ {localidade_count} localidades fixas\n')

        total = StoreDeliveryZone.objects.filter(store__in=stores).count()
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'✅ {total} zonas criadas!'))
        self.stdout.write('=' * 60 + '\n')
