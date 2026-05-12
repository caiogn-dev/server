from django.db import migrations
from apps.core.fields import EncryptedCharField


class Migration(migrations.Migration):
    """
    Converte access_token e page_access_token para EncryptedCharField.

    O EncryptedCharField lê valores plaintext legados sem erro e
    os re-criptografa transparentemente no próximo save().
    Não é necessária data migration — a migração é lazy (zero downtime).
    """

    dependencies = [
        ('instagram', '0005_fix_urlfield_max_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instagramaccount',
            name='access_token',
            field=EncryptedCharField(
                max_length=2000,
                help_text='User Access Token ou Instagram Business Token (leitura de mídia, insights).',
            ),
        ),
        migrations.AlterField(
            model_name='instagramaccount',
            name='page_access_token',
            field=EncryptedCharField(
                max_length=2000,
                blank=True,
                default='',
                help_text='Page Access Token da Página Facebook conectada. Necessário para enviar DMs via Instagram.',
            ),
        ),
    ]
