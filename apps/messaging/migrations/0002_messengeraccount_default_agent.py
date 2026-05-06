from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0007_alter_agent_base_url_alter_agent_model_name_and_more'),
        ('messaging', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='messengeraccount',
            name='default_agent',
            field=models.ForeignKey(
                blank=True,
                help_text='Agente IA padrão para resposta automática em conversas do Messenger',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='messenger_accounts',
                to='agents.agent',
            ),
        ),
        migrations.AddField(
            model_name='messengeraccount',
            name='auto_response_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Habilitar resposta automática de IA via Messenger',
            ),
        ),
    ]
