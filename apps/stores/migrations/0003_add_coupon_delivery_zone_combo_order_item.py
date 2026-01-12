# Generated migration for unified coupon, delivery zone, and combo order items

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0002_add_cart_combo_product_types'),
    ]

    operations = [
        # StoreCoupon
        migrations.CreateModel(
            name='StoreCoupon',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code', models.CharField(db_index=True, max_length=50)),
                ('description', models.TextField(blank=True)),
                ('discount_type', models.CharField(choices=[('percentage', 'Percentage'), ('fixed', 'Fixed Amount')], default='percentage', max_length=20)),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=10)),
                ('min_purchase', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('max_discount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('usage_limit', models.PositiveIntegerField(blank=True, null=True)),
                ('usage_limit_per_user', models.PositiveIntegerField(blank=True, null=True)),
                ('used_count', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('valid_from', models.DateTimeField()),
                ('valid_until', models.DateTimeField()),
                ('first_order_only', models.BooleanField(default=False)),
                ('applicable_categories', models.JSONField(blank=True, default=list, help_text='List of category IDs')),
                ('applicable_products', models.JSONField(blank=True, default=list, help_text='List of product IDs')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coupons', to='stores.store')),
            ],
            options={
                'verbose_name': 'Store Coupon',
                'verbose_name_plural': 'Store Coupons',
                'db_table': 'store_coupons',
                'ordering': ['-created_at'],
                'unique_together': {('store', 'code')},
            },
        ),
        # StoreDeliveryZone
        migrations.CreateModel(
            name='StoreDeliveryZone',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('zone_type', models.CharField(choices=[('distance_band', 'Distance Band'), ('custom_distance', 'Custom Distance Range'), ('zip_range', 'ZIP Code Range'), ('polygon', 'Custom Polygon'), ('time_based', 'Time-based (Isochrone)')], default='distance_band', max_length=20)),
                ('distance_band', models.CharField(blank=True, choices=[('0_2', '0-2 km'), ('2_5', '2-5 km'), ('5_8', '5-8 km'), ('8_12', '8-12 km'), ('12_15', '12-15 km'), ('15_20', '15-20 km'), ('20_30', '20-30 km'), ('30_plus', '30+ km')], max_length=10, null=True)),
                ('min_km', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('max_km', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('zip_code_start', models.CharField(blank=True, max_length=8, null=True)),
                ('zip_code_end', models.CharField(blank=True, max_length=8, null=True)),
                ('min_minutes', models.PositiveIntegerField(blank=True, null=True)),
                ('max_minutes', models.PositiveIntegerField(blank=True, null=True)),
                ('polygon_coordinates', models.JSONField(blank=True, default=list, help_text='GeoJSON coordinates [[lng, lat], ...]')),
                ('delivery_fee', models.DecimalField(decimal_places=2, max_digits=10)),
                ('min_fee', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('fee_per_km', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('estimated_minutes', models.PositiveIntegerField(default=30)),
                ('estimated_days', models.PositiveIntegerField(default=0)),
                ('color', models.CharField(default='#722F37', help_text='Hex color for map', max_length=7)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_zones', to='stores.store')),
            ],
            options={
                'verbose_name': 'Delivery Zone',
                'verbose_name_plural': 'Delivery Zones',
                'db_table': 'store_delivery_zones',
                'ordering': ['store', 'sort_order', 'distance_band', 'min_km'],
            },
        ),
        # StoreOrderComboItem
        migrations.CreateModel(
            name='StoreOrderComboItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('combo_name', models.CharField(max_length=255)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=10)),
                ('customizations', models.JSONField(blank=True, default=dict)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('combo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='stores.storecombo')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='combo_items', to='stores.storeorder')),
            ],
            options={
                'verbose_name': 'Order Combo Item',
                'verbose_name_plural': 'Order Combo Items',
                'db_table': 'store_order_combo_items',
            },
        ),
    ]
