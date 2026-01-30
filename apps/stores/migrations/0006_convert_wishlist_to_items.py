from django.db import migrations, connection, models
import django.db.models as dj_models
import uuid
from datetime import datetime


def forwards(apps, schema_editor):
    """Convert old wishlist+m2m schema to per-item wishlist rows.

    - Create a temporary table `store_wishlists_new` with the desired schema
    - Copy each (wishlist, product) pair into a new row
    - Drop old tables and rename new table to `store_wishlists`
    """
    with connection.cursor() as cursor:
        vendor = connection.vendor

        if vendor == 'postgresql':
            # Create a new table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS store_wishlists_new (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    created_at timestamp with time zone DEFAULT now(),
                    updated_at timestamp with time zone DEFAULT now(),
                    store_id uuid NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
                    customer_phone varchar(20) NOT NULL DEFAULT '',
                    customer_email varchar(254) DEFAULT '',
                    product_id uuid NOT NULL REFERENCES store_products(id) ON DELETE CASCADE
                )
            """)

            # Migrate data from old M2M table into the new rows
            cursor.execute("""
                INSERT INTO store_wishlists_new (id, store_id, customer_phone, customer_email, product_id, created_at)
                SELECT gen_random_uuid(), sw.store_id, '', '', swp.storeproduct_id, now()
                FROM store_wishlists_products swp
                JOIN store_wishlists sw ON swp.storewishlist_id = sw.id
            """)

            # Drop old M2M table and old wishlists table
            cursor.execute("DROP TABLE IF EXISTS store_wishlists_products")
            cursor.execute("DROP TABLE IF EXISTS store_wishlists")

            # Rename new table
            cursor.execute("ALTER TABLE store_wishlists_new RENAME TO store_wishlists")

        else:
            # SQLite fallback - use Python to generate uuids and perform inserts
            # Create new table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS store_wishlists_new (
                    id char(36) PRIMARY KEY,
                    created_at datetime DEFAULT CURRENT_TIMESTAMP,
                    updated_at datetime DEFAULT CURRENT_TIMESTAMP,
                    store_id char(36) NOT NULL REFERENCES stores(id),
                    customer_phone varchar(20) NOT NULL DEFAULT '',
                    customer_email varchar(254) DEFAULT '',
                    product_id char(36) NOT NULL REFERENCES store_products(id)
                )
            ''')

            # Fetch old m2m rows
            cursor.execute("SELECT storewishlist_id, storeproduct_id FROM store_wishlists_products")
            rows = cursor.fetchall()

            if rows:
                # Map wishlist id to store_id
                cursor.execute("SELECT id, store_id FROM store_wishlists")
                wishlist_map = {r[0]: r[1] for r in cursor.fetchall()}

                for swp_id, product_id in rows:
                    store_id = wishlist_map.get(swp_id)
                    if not store_id:
                        continue
                    new_id = str(uuid.uuid4())
                    now = datetime.utcnow().isoformat()
                    cursor.execute(
                        "INSERT INTO store_wishlists_new (id, store_id, customer_phone, customer_email, product_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id, store_id, '', '', product_id, now)
                    )

            # Drop old tables and rename
            cursor.execute("DROP TABLE IF EXISTS store_wishlists_products")
            cursor.execute("DROP TABLE IF EXISTS store_wishlists")
            cursor.execute("ALTER TABLE store_wishlists_new RENAME TO store_wishlists")


def reverse(apps, schema_editor):
    # Non-reversible migration (data loss when converting back to old format). No-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0005_storewishlist_customer_phone_default'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
        # Update Django state to match the current model: remove old `user` and `products` fields,
        # add `customer_phone`, `customer_email`, and `product` fields, and set unique_together.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='storewishlist', name='user'),
                migrations.RemoveField(model_name='storewishlist', name='products'),
                migrations.AddField(
                    model_name='storewishlist',
                    name='customer_phone',
                    field=models.CharField(blank=True, default='', max_length=20),
                ),
                migrations.AddField(
                    model_name='storewishlist',
                    name='customer_email',
                    field=models.EmailField(blank=True, max_length=254),
                ),
                migrations.AddField(
                    model_name='storewishlist',
                    name='product',
                    field=models.ForeignKey(on_delete=dj_models.deletion.CASCADE, related_name='wishlisted_by', to='stores.storeproduct'),
                ),
                migrations.AlterUniqueTogether(
                    name='storewishlist',
                    unique_together={('store', 'customer_phone', 'product')},
                ),
            ],
            database_operations=[],
        ),
    ]
