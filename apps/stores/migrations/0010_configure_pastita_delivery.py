"""
Migration to configure Pastita delivery settings for dynamic pricing.
"""
from decimal import Decimal
from django.db import migrations


def configure_pastita_delivery(apps, schema_editor):
    """
    Configure Pastita store delivery settings for dynamic pricing.
    
    Formula: base_fee + (distance - free_km) * fee_per_km
    Example for 8.92 km: 5.00 + (8.92 - 2.0) * 1.00 = R$ 11.92
    """
    Store = apps.get_model('stores', 'Store')
    
    try:
        store = Store.objects.get(slug='pastita')
        
        # Set default delivery fee (base fee)
        store.default_delivery_fee = Decimal('5.00')
        
        # Configure metadata for dynamic pricing
        metadata = store.metadata or {}
        metadata['delivery_base_fee'] = 5.0      # Base fee (minimum)
        metadata['delivery_fee_per_km'] = 1.0    # R$ 1.00 per km after threshold
        metadata['delivery_free_km'] = 2.0       # First 2 km included in base fee
        metadata['delivery_max_fee'] = 25.0      # Maximum delivery fee
        metadata['max_delivery_distance_km'] = 20  # Max delivery distance
        metadata['max_delivery_time_minutes'] = 60  # Max delivery time
        
        store.metadata = metadata
        store.save(update_fields=['default_delivery_fee', 'metadata'])
        
        print(f'✅ Configured Pastita delivery settings:')
        print(f'   Base fee: R$ 5.00')
        print(f'   Fee per km: R$ 1.00 (after 2 km)')
        print(f'   Max fee: R$ 25.00')
        print(f'   Max distance: 20 km')
        
    except Store.DoesNotExist:
        print('⚠️ Pastita store not found')


def reverse_migration(apps, schema_editor):
    """Reverse migration - reset to defaults."""
    Store = apps.get_model('stores', 'Store')
    try:
        store = Store.objects.get(slug='pastita')
        store.default_delivery_fee = Decimal('10.00')
        store.save(update_fields=['default_delivery_fee'])
    except Store.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0009_force_dynamic_pricing'),
    ]

    operations = [
        migrations.RunPython(configure_pastita_delivery, reverse_migration),
    ]
