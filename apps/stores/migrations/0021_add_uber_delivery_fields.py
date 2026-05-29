# Generated migration for Uber delivery fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0020_migrate_staff_to_team_members'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeorder',
            name='delivery_provider',
            field=models.CharField(
                choices=[('none', 'None'), ('toca', 'Toca Delivery'), ('uber', 'Uber Eats')],
                db_index=True,
                default='none',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_delivery_request_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Uber's delivery request ID",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_driver_id',
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_driver_name',
            field=models.CharField(
                blank=True,
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_driver_phone',
            field=models.CharField(
                blank=True,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_vehicle_info',
            field=models.CharField(
                blank=True,
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_eta_minutes',
            field=models.IntegerField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_pickup_instructions',
            field=models.TextField(
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='uber_created_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name='storeorder',
            index=models.Index(fields=['delivery_provider'], name='stores_stor_deliver_a12b3c'),
        ),
        migrations.AddIndex(
            model_name='storeorder',
            index=models.Index(fields=['uber_delivery_request_id'], name='stores_stor_uber_de_f4e5d6'),
        ),
    ]
