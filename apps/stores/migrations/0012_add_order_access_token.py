# Generated migration for adding access_token field to StoreOrder
# This token is required for secure public access to order details
# This migration is idempotent - safe to run multiple times
# Uses SeparateDatabaseAndState to handle both DB and Django state

import secrets
from django.db import migrations, models, connection


def safe_add_access_token(apps, schema_editor):
    """
    Safely add access_token field and generate tokens for existing orders.
    This function is idempotent - safe to run multiple times.
    Uses raw SQL to avoid ORM model state issues.
    """
    with connection.cursor() as cursor:
        # Check if column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'store_orders' AND column_name = 'access_token'
        """)
        column_exists = cursor.fetchone() is not None
        
        if not column_exists:
            # Add the column
            cursor.execute("""
                ALTER TABLE store_orders 
                ADD COLUMN access_token VARCHAR(64) DEFAULT '' NOT NULL
            """)
        
        # Generate tokens for orders without one (using raw SQL)
        cursor.execute("""
            SELECT id FROM store_orders WHERE access_token = '' OR access_token IS NULL
        """)
        orders_without_token = cursor.fetchall()
        
        for (order_id,) in orders_without_token:
            token = secrets.token_urlsafe(32)
            cursor.execute("""
                UPDATE store_orders SET access_token = %s WHERE id = %s
            """, [token, order_id])
        
        # Check if any index/constraint on access_token exists
        cursor.execute("""
            SELECT 1 FROM pg_indexes 
            WHERE tablename = 'store_orders' 
            AND indexdef LIKE '%%access_token%%'
            LIMIT 1
        """)
        index_exists = cursor.fetchone() is not None
        
        if not index_exists:
            # Create unique index
            cursor.execute("""
                CREATE UNIQUE INDEX store_orders_access_token_key 
                ON store_orders (access_token)
            """)


def reverse_migration(apps, schema_editor):
    """Reverse migration - no-op to preserve data."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0011_add_pix_ticket_url'),
    ]

    operations = [
        # Use SeparateDatabaseAndState to:
        # 1. Run the database operations via RunPython (idempotent)
        # 2. Update Django's state to know the field exists
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(safe_add_access_token, reverse_migration),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='storeorder',
                    name='access_token',
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default='',
                        help_text='Secure token for public order access (payment page, tracking)',
                        max_length=64,
                        unique=True
                    ),
                ),
            ],
        ),
    ]
