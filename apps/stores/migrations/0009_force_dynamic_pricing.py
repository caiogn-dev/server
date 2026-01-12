"""
Migration to force dynamic pricing by deactivating all delivery zones.
"""
from django.db import migrations


def force_dynamic_pricing(apps, schema_editor):
    """
    Deactivate ALL delivery zones to force dynamic pricing.
    This ensures consistent pricing based on actual distance.
    """
    StoreDeliveryZone = apps.get_model('stores', 'StoreDeliveryZone')
    
    # List all zones for debugging
    print('📋 Current delivery zones:')
    all_zones = StoreDeliveryZone.objects.all()
    for zone in all_zones:
        print(f'  - {zone.name}: type={zone.zone_type}, active={zone.is_active}, fee={zone.delivery_fee}, min_km={zone.min_km}, max_km={zone.max_km}')
    
    # Deactivate ALL zones to force dynamic pricing
    updated = StoreDeliveryZone.objects.filter(is_active=True).update(is_active=False)
    
    print(f'✅ Deactivated {updated} delivery zone(s) - dynamic pricing now active')


def reverse_migration(apps, schema_editor):
    """Reverse migration - no action."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0008_cleanup_delivery_zones'),
    ]

    operations = [
        migrations.RunPython(force_dynamic_pricing, reverse_migration),
    ]
