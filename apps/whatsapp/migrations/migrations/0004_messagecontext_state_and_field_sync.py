# Generated manually to align migration state with the existing MessageContext table.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0003_sync_message_context_and_analytics'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='messagecontext',
                    name='id',
                    field=models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name='advancedtemplate',
            name='components',
            field=models.JSONField(
                default=list,
                help_text='Componentes no formato da API do Meta',
                verbose_name='Componentes',
            ),
        ),
        migrations.AlterField(
            model_name='advancedtemplate',
            name='config',
            field=models.JSONField(
                default=dict,
                help_text='Configuração específica por tipo',
                verbose_name='Configuração',
            ),
        ),
        migrations.AlterField(
            model_name='messagecontext',
            name='quoted_message_id',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='ID Mensagem Citada'),
        ),
        migrations.AlterField(
            model_name='whatsappanalytics',
            name='account',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='analytics',
                to='whatsapp.whatsappaccount',
                verbose_name='Conta WhatsApp',
            ),
        ),
        migrations.AlterField(
            model_name='whatsappanalyticsreport',
            name='schedule_day',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Dia da semana (0-6) para semanal, ou dia do mês (1-31) para mensal',
                null=True,
                verbose_name='Dia do Agendamento',
            ),
        ),
    ]
