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


def add_fields_and_create_wishlist(apps, schema_editor):
    """
    Add columns to StoreProduct and create StoreWishlist table.
    Uses raw SQL with IF NOT EXISTS for idempotency.
    """
    from django.db import connection
    
    with connection.cursor() as cursor:
        vendor = connection.vendor
        
        if vendor == 'postgresql':
            # PostgreSQL - use IF NOT EXISTS
            
            # Add product_type_id column
            try:
                cursor.execute("""
                    ALTER TABLE stores_storeproduct 
                    ADD COLUMN IF NOT EXISTS product_type_id uuid REFERENCES stores_storeproducttype(id) ON DELETE SET NULL
                """)
            except Exception:
                pass
            
            # Add type_attributes column
            try:
                cursor.execute("""
                    ALTER TABLE stores_storeproduct 
                    ADD COLUMN IF NOT EXISTS type_attributes jsonb DEFAULT '{}'::jsonb
                """)
            except Exception:
                pass
            
            # Create store_wishlists table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS store_wishlists (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    created_at timestamp with time zone DEFAULT now(),
                    updated_at timestamp with time zone DEFAULT now(),
                    store_id uuid NOT NULL REFERENCES stores_store(id) ON DELETE CASCADE,
                    user_id integer NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
                    UNIQUE(store_id, user_id)
                )
            """)
            
            # Create M2M table for wishlist products
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS store_wishlists_products (
                    id serial PRIMARY KEY,
                    storewishlist_id uuid NOT NULL REFERENCES store_wishlists(id) ON DELETE CASCADE,
                    storeproduct_id uuid NOT NULL REFERENCES stores_storeproduct(id) ON DELETE CASCADE,
                    UNIQUE(storewishlist_id, storeproduct_id)
                )
            """)
            
        else:
            # SQLite - check columns first
            cursor.execute("PRAGMA table_info(stores_storeproduct)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'product_type_id' not in columns:
                try:
                    cursor.execute("""
                        ALTER TABLE stores_storeproduct 
                        ADD COLUMN product_type_id char(36) REFERENCES stores_storeproducttype(id)
                    """)
                except Exception:
                    pass
            
            if 'type_attributes' not in columns:
                try:
                    cursor.execute("""
                        ALTER TABLE stores_storeproduct 
                        ADD COLUMN type_attributes text DEFAULT '{}'
                    """)
                except Exception:
                    pass
            
            # Check if wishlist table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='store_wishlists'
            """)
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE store_wishlists (
                        id char(36) PRIMARY KEY,
                        created_at datetime DEFAULT CURRENT_TIMESTAMP,
                        updated_at datetime DEFAULT CURRENT_TIMESTAMP,
                        store_id char(36) NOT NULL REFERENCES stores_store(id),
                        user_id integer NOT NULL REFERENCES auth_user(id),
                        UNIQUE(store_id, user_id)
                    )
                """)
            
            # Check if M2M table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='store_wishlists_products'
            """)
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE store_wishlists_products (
                        id integer PRIMARY KEY AUTOINCREMENT,
                        storewishlist_id char(36) NOT NULL REFERENCES store_wishlists(id),
                        storeproduct_id char(36) NOT NULL REFERENCES stores_storeproduct(id),
                        UNIQUE(storewishlist_id, storeproduct_id)
                    )
                """)


def reverse_migration(apps, schema_editor):
    """Reverse migration - no-op to preserve data."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stores', '0003_add_coupon_delivery_zone_combo_order_item'),
    ]

    operations = [
        # Use RunPython for all database operations (idempotent)
        migrations.RunPython(add_fields_and_create_wishlist, reverse_migration),
        
        # State-only operations to register models with Django ORM
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
                migrations.AddField(
                    model_name='storeproduct',
                    name='type_attributes',
                    field=models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Values for custom fields defined by the product type'
                    ),
                ),
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
            ],
            database_operations=[],  # Already handled by RunPython above
        ),
    ]
