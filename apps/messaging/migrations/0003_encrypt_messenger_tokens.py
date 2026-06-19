"""
Converte page_access_token e app_secret do MessengerAccount para EncryptedCharField.

O EncryptedCharField lê valores em texto claro legados sem erro e os re-encripta
na próxima gravação, permitindo uma migração zero-downtime. Nenhum dado é perdido.
"""
from django.db import migrations
from apps.core.fields import EncryptedCharField


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0002_messengeraccount_default_agent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='messengeraccount',
            name='page_access_token',
            field=EncryptedCharField(
                max_length=1000,
                help_text='Page Access Token (encrypted)',
            ),
        ),
        migrations.AlterField(
            model_name='messengeraccount',
            name='app_secret',
            field=EncryptedCharField(
                max_length=500,
                null=True,
                blank=True,
                help_text='App Secret (encrypted)',
            ),
        ),
    ]
