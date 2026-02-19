# Generated migration for adding missing fields to Agent models

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0003_merge'),
    ]

    operations = [
        # Add max_context_messages to Agent model
        migrations.AddField(
            model_name='agent',
            name='max_context_messages',
            field=models.PositiveIntegerField(
                default=10,
                help_text='Número máximo de mensagens históricas para manter no contexto',
                verbose_name='Máximo de mensagens de contexto'
            ),
        ),
        # Add user_id to AgentConversation model
        migrations.AddField(
            model_name='agentconversation',
            name='user_id',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name='ID do Usuário'
            ),
        ),
        # Add metadata to AgentConversation model
        migrations.AddField(
            model_name='agentconversation',
            name='metadata',
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name='Metadados'
            ),
        ),
        # Add metadata to AgentMessage model
        migrations.AddField(
            model_name='agentmessage',
            name='metadata',
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name='Metadados'
            ),
        ),
    ]
