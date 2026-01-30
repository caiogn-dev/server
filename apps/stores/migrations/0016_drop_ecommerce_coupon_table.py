from django.db import migrations, connection


def drop_ecommerce_coupon_table(apps, schema_editor):
    """Drop the legacy ecommerce_coupon table (if it still exists)."""
    with connection.cursor() as cursor:
        vendor = connection.vendor
        try:
            if vendor == 'postgresql':
                cursor.execute('DROP TABLE IF EXISTS ecommerce_coupon CASCADE;')
            else:
                cursor.execute('DROP TABLE IF EXISTS ecommerce_coupon;')
        except Exception:
            # Table might already be gone or not accessible.
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0015_alter_storewishlist_options_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_ecommerce_coupon_table, migrations.RunPython.noop),
    ]
