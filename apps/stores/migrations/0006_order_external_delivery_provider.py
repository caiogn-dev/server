from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0005_store_url_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeorder',
            name='external_delivery_provider',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='external_delivery_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='external_delivery_code',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='external_delivery_status',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='external_delivery_url',
            field=models.URLField(blank=True, default='', max_length=500),
        ),
    ]
