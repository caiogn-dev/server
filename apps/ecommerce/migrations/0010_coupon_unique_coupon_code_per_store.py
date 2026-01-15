# Generated manually to fix migration conflict
# This migration is a no-op since the constraint was already added in 0009

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    This migration exists to satisfy Django's migration history.
    The constraint 'unique_coupon_code_per_store' was already added in migration 0009.
    This migration does nothing but marks itself as applied.
    """

    dependencies = [
        ('ecommerce', '0009_alter_coupon_store_alter_deliveryzone_store_and_more'),
    ]

    operations = [
        # No operations - constraint already exists from 0009
        # This migration exists only to match the expected migration name
        # in environments where Django auto-generated this migration
    ]
