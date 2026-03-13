from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0009_alter_flowexecutionlog_options_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
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
