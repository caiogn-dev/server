from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0004_encrypt_payment_credentials'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE stores ADD COLUMN IF NOT EXISTS website_url varchar(200) NOT NULL DEFAULT '';
                        ALTER TABLE stores ADD COLUMN IF NOT EXISTS menu_url varchar(200) NOT NULL DEFAULT '';
                        ALTER TABLE stores ADD COLUMN IF NOT EXISTS order_url varchar(200) NOT NULL DEFAULT '';
                        ALTER TABLE stores ALTER COLUMN website_url DROP DEFAULT;
                        ALTER TABLE stores ALTER COLUMN menu_url DROP DEFAULT;
                        ALTER TABLE stores ALTER COLUMN order_url DROP DEFAULT;
                    """,
                    reverse_sql="""
                        ALTER TABLE stores DROP COLUMN IF EXISTS order_url;
                        ALTER TABLE stores DROP COLUMN IF EXISTS menu_url;
                        ALTER TABLE stores DROP COLUMN IF EXISTS website_url;
                    """,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='store',
                    name='website_url',
                    field=models.URLField(blank=True, help_text='Store website'),
                ),
                migrations.AddField(
                    model_name='store',
                    name='menu_url',
                    field=models.URLField(blank=True, help_text='Online menu URL'),
                ),
                migrations.AddField(
                    model_name='store',
                    name='order_url',
                    field=models.URLField(blank=True, help_text='Direct order link'),
                ),
            ],
        ),
    ]
