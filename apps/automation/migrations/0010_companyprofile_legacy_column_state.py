from django.db import migrations, models


def add_columns_if_missing(apps, schema_editor):
    """Add whatsapp_number and address to company_profiles if they don't exist yet.

    Production databases already have these columns (added before Django migrations
    tracked them). Dev/test databases need them created. We try to add and silently
    ignore the error if the column already exists.
    """
    db = schema_editor.connection
    with db.cursor() as cursor:
        # Detect existing columns
        if db.vendor == 'sqlite':
            cursor.execute("PRAGMA table_info(company_profiles)")
            existing = {row[1] for row in cursor.fetchall()}
        else:
            # PostgreSQL / MySQL
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'company_profiles'"
            )
            existing = {row[0] for row in cursor.fetchall()}

        if 'whatsapp_number' not in existing:
            schema_editor.execute(
                "ALTER TABLE company_profiles ADD COLUMN whatsapp_number VARCHAR(20) NOT NULL DEFAULT ''"
            )
        if 'address' not in existing:
            schema_editor.execute(
                "ALTER TABLE company_profiles ADD COLUMN address TEXT NOT NULL DEFAULT ''"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0009_alter_flowexecutionlog_options_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Use RunPython to add columns only when missing (safe for both
            # production — where they already exist — and fresh dev/test DBs).
            database_operations=[
                migrations.RunPython(add_columns_if_missing, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='companyprofile',
                    name='_legacy_whatsapp_number',
                    field=models.CharField(
                        blank=True,
                        db_column='whatsapp_number',
                        default='',
                        editable=False,
                        max_length=20,
                    ),
                ),
                migrations.AddField(
                    model_name='companyprofile',
                    name='_legacy_address',
                    field=models.TextField(
                        blank=True,
                        db_column='address',
                        default='',
                        editable=False,
                    ),
                ),
            ],
        ),
    ]
