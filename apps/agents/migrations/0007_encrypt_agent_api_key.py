from django.db import migrations, models


def encrypt_existing_api_keys(apps, schema_editor):
    from apps.core.utils import token_encryption

    Agent = apps.get_model('agents', 'Agent')
    for agent in Agent.objects.exclude(api_key_encrypted=''):
        value = agent.api_key_encrypted
        try:
            token_encryption.decrypt(value)  # already encrypted
        except Exception:
            agent.api_key_encrypted = token_encryption.encrypt(value)
            agent.save(update_fields=['api_key_encrypted'])


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0006_agent_max_context_messages_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='agent',
            old_name='api_key',
            new_name='api_key_encrypted',
        ),
        migrations.AlterField(
            model_name='agent',
            name='api_key_encrypted',
            field=models.TextField(blank=True, verbose_name='API Key (criptografada)'),
        ),
        migrations.RunPython(
            encrypt_existing_api_keys,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
