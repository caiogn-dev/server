from decimal import Decimal
from django.db import migrations, models


def map_distance_band(apps, schema_editor):
    DeliveryZone = apps.get_model('ecommerce', 'DeliveryZone')
    for zone in DeliveryZone.objects.all():
        if zone.distance_band:
            continue
        min_km = zone.min_km or Decimal('0')
        max_km = zone.max_km or min_km
        if max_km <= Decimal('2'):
            band = '0_2'
        elif max_km <= Decimal('5'):
            band = '2_5'
        elif max_km <= Decimal('8'):
            band = '5_8'
        elif max_km <= Decimal('12'):
            band = '8_12'
        elif max_km <= Decimal('15'):
            band = '12_15'
        else:
            band = '15_20'
        zone.distance_band = band
        zone.save(update_fields=['distance_band'])


class Migration(migrations.Migration):
    dependencies = [
        ('ecommerce', '0004_delivery_distance_store_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryzone',
            name='distance_band',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=10,
                choices=[
                    ('0_2', '0-2 km'),
                    ('2_5', '2-5 km'),
                    ('5_8', '5-8 km'),
                    ('8_12', '8-12 km'),
                    ('12_15', '12-15 km'),
                    ('15_20', '15-20 km'),
                ],
            ),
        ),
        migrations.RunPython(map_distance_band, migrations.RunPython.noop),
    ]
