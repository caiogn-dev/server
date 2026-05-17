"""
Migração de segurança: criptografa o access_token das contas do Instagram.

Renomeia a coluna access_token para access_token_encrypted e criptografa
todos os valores existentes usando a mesma chave Fernet utilizada pelo
WhatsApp (apps.core.utils.token_encryption).
"""
from django.db import migrations, models


def encrypt_existing_tokens(apps, schema_editor):
    from apps.core.utils import token_encryption
    InstagramAccount = apps.get_model('instagram', 'InstagramAccount')
    updated = 0
    for account in InstagramAccount.objects.all():
        raw = account.access_token or ''
        account.access_token_encrypted = token_encryption.encrypt(raw) if raw else ''
        account.save(update_fields=['access_token_encrypted'])
        updated += 1
    if updated:
        print(f"\n  Criptografados {updated} tokens de contas Instagram.")


def decrypt_tokens_back(apps, schema_editor):
    from apps.core.utils import token_encryption
    InstagramAccount = apps.get_model('instagram', 'InstagramAccount')
    for account in InstagramAccount.objects.all():
        encrypted = account.access_token_encrypted or ''
        try:
            account.access_token = token_encryption.decrypt(encrypted) if encrypted else ''
        except Exception:
            account.access_token = ''
        account.save(update_fields=['access_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('instagram', '0001_initial'),
    ]

    operations = [
        # 1. Adiciona nova coluna criptografada (nullable temporariamente via default)
        migrations.AddField(
            model_name='instagramaccount',
            name='access_token_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        # 2. Criptografa valores existentes
        migrations.RunPython(
            encrypt_existing_tokens,
            reverse_code=decrypt_tokens_back,
        ),
        # 3. Remove a coluna antiga de texto plano
        migrations.RemoveField(
            model_name='instagramaccount',
            name='access_token',
        ),
    ]
