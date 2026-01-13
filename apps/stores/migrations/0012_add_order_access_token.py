# Generated migration for adding access_token field to StoreOrder
# This token is required for secure public access to order details
# This migration is idempotent - safe to run multiple times

import secrets
from django.db import migrations, connection


def safe_add_access_token(apps, schema_editor):
    """
    Safely add access_token field and generate tokens for existing orders.
    This function is idempotent - safe to run multiple times.
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
    
    # Generate tokens for orders without one
    StoreOrder = apps.get_model('stores', 'StoreOrder')
    orders_without_token = StoreOrder.objects.filter(access_token='')
    for order in orders_without_token:
        order.access_token = secrets.token_urlsafe(32)
        order.save(update_fields=['access_token'])
    
    # Add unique constraint if not exists (using raw SQL for idempotency)
    with connection.cursor() as cursor:
        # Check if any index/constraint on access_token exists
        cursor.execute("""
            SELECT 1 FROM pg_indexes 
            WHERE tablename = 'store_orders' 
            AND indexdef LIKE '%access_token%'
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
        migrations.RunPython(safe_add_access_token, reverse_migration),
    ]
