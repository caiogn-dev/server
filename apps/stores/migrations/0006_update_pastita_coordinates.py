"""
Migration to update Pastita store coordinates to correct location (Ivoneth Banqueteria).
"""
from decimal import Decimal
from django.db import migrations


def update_pastita_coordinates(apps, schema_editor):
    Store = apps.get_model('stores', 'Store')
    try:
        store = Store.objects.get(slug='pastita')
        # Coordenadas corretas do Google Maps - Ivoneth Banqueteria
        store.latitude = Decimal('-10.185260')
        store.longitude = Decimal('-48.303478')
        store.save(update_fields=['latitude', 'longitude'])
        print(f"Updated Pastita coordinates to (-10.185260, -48.303478)")
    except Store.DoesNotExist:
        print("Pastita store not found, skipping coordinate update")
    
    # Also update any other stores that might have wrong coordinates
    stores_updated = Store.objects.filter(
        slug='pastita'
    ).update(
        latitude=Decimal('-10.185260'),
        longitude=Decimal('-48.303478')
    )
    print(f"Force updated {stores_updated} store(s)")


def reverse_coordinates(apps, schema_editor):
    Store = apps.get_model('stores', 'Store')
    try:
        store = Store.objects.get(slug='pastita')
        store.latitude = Decimal('-10.1847')
        store.longitude = Decimal('-48.3337')
        store.save(update_fields=['latitude', 'longitude'])
    except Store.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0005_migrate_pastita_data'),
    ]

    operations = [
        migrations.RunPython(update_pastita_coordinates, reverse_coordinates),
    ]
