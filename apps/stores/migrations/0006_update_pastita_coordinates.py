"""
Migration to update Pastita store coordinates to correct location (Ivoneth Banqueteria).
"""
from decimal import Decimal
from django.db import migrations


def update_pastita_coordinates(apps, schema_editor):
    Store = apps.get_model('stores', 'Store')
    # Coordenadas exatas da Ivoneth Banqueteria/Pastita
    CORRECT_LAT = Decimal('-10.1854332')
    CORRECT_LNG = Decimal('-48.3038653')
    
    try:
        store = Store.objects.get(slug='pastita')
        store.latitude = CORRECT_LAT
        store.longitude = CORRECT_LNG
        store.save(update_fields=['latitude', 'longitude'])
        print(f"Updated Pastita coordinates to ({CORRECT_LAT}, {CORRECT_LNG})")
    except Store.DoesNotExist:
        print("Pastita store not found, skipping coordinate update")
    
    # Force update to ensure correct coordinates
    stores_updated = Store.objects.filter(slug='pastita').update(
        latitude=CORRECT_LAT,
        longitude=CORRECT_LNG
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
