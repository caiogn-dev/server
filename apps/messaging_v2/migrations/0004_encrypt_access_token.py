from django.db import migrations, models


def encrypt_existing_tokens(apps, schema_editor):
    from apps.core.utils import token_encryption

    PlatformAccount = apps.get_model('messaging_v2', 'PlatformAccount')
    for account in PlatformAccount.objects.exclude(access_token_encrypted=''):
        value = account.access_token_encrypted
        try:
            token_encryption.decrypt(value)
        except Exception:
            account.access_token_encrypted = token_encryption.encrypt(value)
            account.save(update_fields=['access_token_encrypted'])


class Migration(migrations.Migration):

    dependencies = [
        ('messaging_v2', '0003_add_platform_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='platformaccount',
            old_name='access_token',
            new_name='access_token_encrypted',
        ),
        migrations.AlterField(
            model_name='platformaccount',
            name='access_token_encrypted',
            field=models.TextField(blank=True, verbose_name='Access Token (criptografado)'),
        ),
        migrations.RunPython(encrypt_existing_tokens, migrations.RunPython.noop),
    ]
