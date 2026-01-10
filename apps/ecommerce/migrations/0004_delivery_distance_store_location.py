from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('ecommerce', '0003_checkout_scheduled_date_checkout_scheduled_time_slot_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryzone',
            name='min_km',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name='deliveryzone',
            name='max_km',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name='deliveryzone',
            name='min_fee',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='deliveryzone',
            name='zip_code_start',
            field=models.CharField(blank=True, max_length=8, null=True),
        ),
        migrations.AlterField(
            model_name='deliveryzone',
            name='zip_code_end',
            field=models.CharField(blank=True, max_length=8, null=True),
        ),
        migrations.CreateModel(
            name='StoreLocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=100)),
                ('zip_code', models.CharField(max_length=8)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=50)),
                ('latitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Store Location',
                'verbose_name_plural': 'Store Locations',
            },
        ),
        migrations.CreateModel(
            name='ZipCodeGeo',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('zip_code', models.CharField(max_length=8, unique=True)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=50)),
                ('latitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'ZIP Geolocation',
                'verbose_name_plural': 'ZIP Geolocations',
            },
        ),
    ]
