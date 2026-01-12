"""
Migration to add:
1. product_type FK and type_attributes to StoreProduct for dynamic product types
2. StoreWishlist for user wishlists per store

Product types are fully dynamic - stores can create their own types (like Molho, Carne, Rondelli)
with custom field definitions stored in StoreProductType.custom_fields.
Products store their type-specific values in type_attributes JSONField.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stores', '0003_add_coupon_delivery_zone_combo_order_item'),
    ]

    operations = [
        # Add product_type FK to StoreProduct
        migrations.AddField(
            model_name='storeproduct',
            name='product_type',
            field=models.ForeignKey(
                blank=True,
                help_text='Product type defines custom fields for this product',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='products',
                to='stores.storeproducttype'
            ),
        ),
        
        # Add type_attributes JSONField to StoreProduct
        migrations.AddField(
            model_name='storeproduct',
            name='type_attributes',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Values for custom fields defined by the product type'
            ),
        ),
        
        # StoreWishlist - User wishlist per store
        migrations.CreateModel(
            name='StoreWishlist',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wishlists', to='stores.store')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='store_wishlists', to=settings.AUTH_USER_MODEL)),
                ('products', models.ManyToManyField(blank=True, related_name='wishlisted_by', to='stores.storeproduct')),
            ],
            options={
                'verbose_name': 'Wishlist',
                'verbose_name_plural': 'Wishlists',
                'db_table': 'store_wishlists',
                'unique_together': {('store', 'user')},
            },
        ),
    ]
