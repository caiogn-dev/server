"""
Migration to cleanup delivery zones and ensure dynamic pricing works.
"""
from django.db import migrations


def cleanup_delivery_zones(apps, schema_editor):
    """
    Deactivate generic delivery zones that override dynamic pricing.
    Only keep zones with specific, meaningful distance ranges.
    """
    StoreDeliveryZone = apps.get_model('stores', 'StoreDeliveryZone')
    
    # Deactivate zones that have very wide ranges (catch-all zones)
    # These prevent dynamic pricing from working correctly
    updated = StoreDeliveryZone.objects.filter(
        zone_type='custom_distance',
        min_km__lte=0,
        max_km__gte=50  # Zones covering 0-50+ km are too generic
    ).update(is_active=False)
    
    print(f'✅ Deactivated {updated} generic delivery zone(s)')
    
    # Also deactivate zones named "Padrão" or "Default" that might be catch-all
    updated2 = StoreDeliveryZone.objects.filter(
        name__in=['Padrão', 'Default', 'Padrao'],
        zone_type='custom_distance'
    ).update(is_active=False)
    
    print(f'✅ Deactivated {updated2} default-named zone(s)')


def reverse_migration(apps, schema_editor):
    """Reverse migration - reactivate zones."""
    StoreDeliveryZone = apps.get_model('stores', 'StoreDeliveryZone')
    StoreDeliveryZone.objects.filter(
        zone_type='custom_distance',
        is_active=False
    ).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0007_fix_pastita_coordinates'),
    ]

    operations = [
        migrations.RunPython(cleanup_delivery_zones, reverse_migration),
    ]
