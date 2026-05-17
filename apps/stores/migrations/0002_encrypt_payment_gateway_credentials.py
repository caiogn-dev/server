"""
Migração de segurança: criptografa as credenciais do StorePaymentGateway.

Renomeia os campos de credenciais para _encrypted e criptografa todos
os valores existentes usando apps.core.utils.token_encryption.

Campos afetados: api_key, api_secret, access_token, webhook_secret, public_key
"""
from django.db import migrations, models


def encrypt_gateway_credentials(apps, schema_editor):
    from apps.core.utils import token_encryption
    StorePaymentGateway = apps.get_model('stores', 'StorePaymentGateway')
    fields_map = {
        'api_key': 'api_key_encrypted',
        'api_secret': 'api_secret_encrypted',
        'access_token': 'access_token_encrypted',
        'webhook_secret': 'webhook_secret_encrypted',
        'public_key': 'public_key_encrypted',
    }
    updated = 0
    for gateway in StorePaymentGateway.objects.all():
        changed = []
        for src, dst in fields_map.items():
            raw = getattr(gateway, src, '') or ''
            setattr(gateway, dst, token_encryption.encrypt(raw) if raw else '')
            changed.append(dst)
        gateway.save(update_fields=changed)
        updated += 1
    if updated:
        print(f"\n  Criptografadas credenciais de {updated} gateways de pagamento.")


def decrypt_gateway_credentials(apps, schema_editor):
    from apps.core.utils import token_encryption
    StorePaymentGateway = apps.get_model('stores', 'StorePaymentGateway')
    fields_map = {
        'api_key_encrypted': 'api_key',
        'api_secret_encrypted': 'api_secret',
        'access_token_encrypted': 'access_token',
        'webhook_secret_encrypted': 'webhook_secret',
        'public_key_encrypted': 'public_key',
    }
    for gateway in StorePaymentGateway.objects.all():
        changed = []
        for src, dst in fields_map.items():
            encrypted = getattr(gateway, src, '') or ''
            try:
                setattr(gateway, dst, token_encryption.decrypt(encrypted) if encrypted else '')
            except Exception:
                setattr(gateway, dst, '')
            changed.append(dst)
        gateway.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),
    ]

    operations = [
        # 1. Adiciona colunas criptografadas
        migrations.AddField(
            model_name='storepaymentgateway',
            name='api_key_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='storepaymentgateway',
            name='api_secret_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='storepaymentgateway',
            name='access_token_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='storepaymentgateway',
            name='webhook_secret_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='storepaymentgateway',
            name='public_key_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        # 2. Criptografa credenciais existentes
        migrations.RunPython(
            encrypt_gateway_credentials,
            reverse_code=decrypt_gateway_credentials,
        ),
        # 3. Remove colunas de texto plano antigas
        migrations.RemoveField(
            model_name='storepaymentgateway',
            name='api_key',
        ),
        migrations.RemoveField(
            model_name='storepaymentgateway',
            name='api_secret',
        ),
        migrations.RemoveField(
            model_name='storepaymentgateway',
            name='access_token',
        ),
        migrations.RemoveField(
            model_name='storepaymentgateway',
            name='webhook_secret',
        ),
        migrations.RemoveField(
            model_name='storepaymentgateway',
            name='public_key',
        ),
    ]
