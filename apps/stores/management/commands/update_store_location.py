"""
Management command to update store location coordinates.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.stores.models import Store


class Command(BaseCommand):
    help = 'Update store location coordinates'

    def add_arguments(self, parser):
        parser.add_argument('--slug', type=str, default='pastita', help='Store slug')
        parser.add_argument('--lat', type=str, required=True, help='Latitude')
        parser.add_argument('--lng', type=str, required=True, help='Longitude')

    def handle(self, *args, **options):
        slug = options['slug']
        lat = Decimal(options['lat'])
        lng = Decimal(options['lng'])

        try:
            store = Store.objects.get(slug=slug)
            old_lat, old_lng = store.latitude, store.longitude
            
            store.latitude = lat
            store.longitude = lng
            store.save(update_fields=['latitude', 'longitude'])
            
            self.stdout.write(self.style.SUCCESS(
                f'Updated {store.name} location:\n'
                f'  Old: ({old_lat}, {old_lng})\n'
                f'  New: ({lat}, {lng})'
            ))
        except Store.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Store with slug "{slug}" not found'))
