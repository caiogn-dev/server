"""
Migração: Criptografar credenciais de gateway de pagamento

Renomeia os campos de credenciais do StorePaymentGateway para campos
_encrypted e criptografa os valores existentes usando token_encryption.
"""
from django.db import migrations, models


def encrypt_existing_credentials(apps, schema_editor):
    """Criptografa credenciais já salvas em texto puro."""
    from apps.core.utils import token_encryption

    StorePaymentGateway = apps.get_model('stores', 'StorePaymentGateway')

    FIELDS = [
        ('api_key_encrypted', 'api_key_encrypted'),
        ('api_secret_encrypted', 'api_secret_encrypted'),
        ('access_token_encrypted', 'access_token_encrypted'),
        ('webhook_secret_encrypted', 'webhook_secret_encrypted'),
        ('public_key_encrypted', 'public_key_encrypted'),
    ]

    for gateway in StorePaymentGateway.objects.all():
        changed = False
        for field_name, _ in FIELDS:
            value = getattr(gateway, field_name, '') or ''
            if not value:
                continue
            # Tenta descriptografar; se falhar, o valor já está em texto puro
            try:
                token_encryption.decrypt(value)
                # Já criptografado — nada a fazer
            except Exception:
                # Texto puro — criptografar agora
                try:
                    setattr(gateway, field_name, token_encryption.encrypt(value))
                    changed = True
                except Exception:
                    pass
        if changed:
            gateway.save(update_fields=[f for f, _ in FIELDS])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),
    ]

    operations = [
        # 1. Renomear campos (mantém os dados; o campo é o mesmo colunado no DB)
        migrations.RenameField(
            model_name='storepaymentgateway',
            old_name='api_key',
            new_name='api_key_encrypted',
        ),
        migrations.RenameField(
            model_name='storepaymentgateway',
            old_name='api_secret',
            new_name='api_secret_encrypted',
        ),
        migrations.RenameField(
            model_name='storepaymentgateway',
            old_name='access_token',
            new_name='access_token_encrypted',
        ),
        migrations.RenameField(
            model_name='storepaymentgateway',
            old_name='webhook_secret',
            new_name='webhook_secret_encrypted',
        ),
        migrations.RenameField(
            model_name='storepaymentgateway',
            old_name='public_key',
            new_name='public_key_encrypted',
        ),
        # 2. Alterar tipos para TextField (tokens criptografados são mais longos)
        migrations.AlterField(
            model_name='storepaymentgateway',
            name='api_key_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='storepaymentgateway',
            name='api_secret_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='storepaymentgateway',
            name='access_token_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='storepaymentgateway',
            name='webhook_secret_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='storepaymentgateway',
            name='public_key_encrypted',
            field=models.TextField(blank=True),
        ),
        # 3. Criptografar dados existentes
        migrations.RunPython(encrypt_existing_credentials, noop_reverse),
    ]
