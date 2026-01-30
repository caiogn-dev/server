from django.db import migrations, connection


def drop_legacy_ecommerce_tables(apps, schema_editor):
    """Drop the legacy ecommerce tables that still reference stores."""
    with connection.cursor() as cursor:
        vendor = connection.vendor
        try:
            if vendor == 'postgresql':
                cursor.execute('DROP TABLE IF EXISTS ecommerce_coupon CASCADE;')
                cursor.execute('DROP TABLE IF EXISTS ecommerce_deliveryzone CASCADE;')
            else:
                cursor.execute('DROP TABLE IF EXISTS ecommerce_coupon;')
                cursor.execute('DROP TABLE IF EXISTS ecommerce_deliveryzone;')
        except Exception:
            # Table might already be gone or not accessible.
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0015_alter_storewishlist_options_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_legacy_ecommerce_tables, migrations.RunPython.noop),
    ]
