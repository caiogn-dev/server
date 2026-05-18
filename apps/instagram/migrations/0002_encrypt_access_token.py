from django.db import migrations, models


def encrypt_existing_tokens(apps, schema_editor):
    from apps.core.utils import token_encryption

    InstagramAccount = apps.get_model('instagram', 'InstagramAccount')
    for account in InstagramAccount.objects.exclude(access_token_encrypted=''):
        value = account.access_token_encrypted
        try:
            token_encryption.decrypt(value)  # already encrypted
        except Exception:
            account.access_token_encrypted = token_encryption.encrypt(value)
            account.save(update_fields=['access_token_encrypted'])


class Migration(migrations.Migration):

    dependencies = [
        ('instagram', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='instagramaccount',
            old_name='access_token',
            new_name='access_token_encrypted',
        ),
        migrations.RunPython(
            encrypt_existing_tokens,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
