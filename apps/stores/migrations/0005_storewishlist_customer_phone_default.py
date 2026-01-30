from django.db import migrations, models
from django.db import connection


def ensure_customer_phone_column(apps, schema_editor):
    """Add `customer_phone` column if it's missing (idempotent)."""
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute("""
                ALTER TABLE store_wishlists
                ADD COLUMN IF NOT EXISTS customer_phone varchar(20) NOT NULL DEFAULT ''
            """)
            # Ensure an index exists
            cursor.execute("CREATE INDEX IF NOT EXISTS store_wishlists_customer_phone_idx ON store_wishlists (customer_phone)")
        else:
            # SQLite: check pragma table_info
            cursor.execute("PRAGMA table_info(store_wishlists)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'customer_phone' not in cols:
                cursor.execute("ALTER TABLE store_wishlists ADD COLUMN customer_phone varchar(20) DEFAULT '' NOT NULL")
                # SQLite creates indexes separately
                try:
                    cursor.execute("CREATE INDEX store_wishlists_customer_phone_idx ON store_wishlists (customer_phone)")
                except Exception:
                    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0004_add_specialized_products_and_wishlist'),
    ]

    operations = [
        migrations.RunPython(ensure_customer_phone_column, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='storewishlist',
                    name='customer_phone',
                    field=models.CharField(blank=True, db_index=True, default='', max_length=20),
                ),
            ],
            database_operations=[],
        ),
    ]
