"""
Migration to fix Pastita store coordinates to exact location.
"""
from decimal import Decimal
from django.db import migrations


def fix_pastita_coordinates(apps, schema_editor):
    """Update Pastita store coordinates to exact Ivoneth Banqueteria location."""
    Store = apps.get_model('stores', 'Store')
    
    # Exact coordinates for Ivoneth Banqueteria/Pastita
    CORRECT_LAT = Decimal('-10.1854332')
    CORRECT_LNG = Decimal('-48.3038653')
    
    stores_updated = Store.objects.filter(slug='pastita').update(
        latitude=CORRECT_LAT,
        longitude=CORRECT_LNG
    )
    print(f'✅ Fixed Pastita coordinates to ({CORRECT_LAT}, {CORRECT_LNG}) - {stores_updated} store(s) updated')


def reverse_migration(apps, schema_editor):
    """Reverse migration - no action needed."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0006_update_pastita_coordinates'),
    ]

    operations = [
        migrations.RunPython(fix_pastita_coordinates, reverse_migration),
    ]
