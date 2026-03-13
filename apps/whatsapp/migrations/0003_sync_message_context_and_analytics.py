# Generated manually to avoid fragile index renames and primary-key churn.

from django.db import migrations, models
import django.db.models.deletion


class AddIndexIfMissing(migrations.AddIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        table_name = model._meta.db_table
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(cursor, table_name)
        if self.index.name in constraints:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        table_name = model._meta.db_table
        with schema_editor.connection.cursor() as cursor:
            columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
            }
        field = to_state.apps.get_model(app_label, self.model_name)._meta.get_field(self.name)
        if field.column in columns:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0002_advancedtemplate_whatsappanalyticsreport_and_more'),
    ]

    operations = [
        AddFieldIfMissing(
            model_name='messagecontext',
            name='message',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='context',
                to='whatsapp.message',
                verbose_name='Mensagem',
            ),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='authentication_conversations',
            field=models.PositiveIntegerField(default=0, verbose_name='Autenticação'),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='business_initiated',
            field=models.PositiveIntegerField(default=0, verbose_name='Iniciadas pelo Negócio'),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='marketing_conversations',
            field=models.PositiveIntegerField(default=0, verbose_name='Marketing'),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='service_conversations',
            field=models.PositiveIntegerField(default=0, verbose_name='Serviço'),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='total_conversations',
            field=models.PositiveIntegerField(default=0, verbose_name='Total Conversações'),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='user_initiated',
            field=models.PositiveIntegerField(default=0, verbose_name='Iniciadas pelo Usuário'),
        ),
        AddFieldIfMissing(
            model_name='whatsappanalytics',
            name='utility_conversations',
            field=models.PositiveIntegerField(default=0, verbose_name='Utilidade'),
        ),
        AddIndexIfMissing(
            model_name='advancedtemplatelog',
            index=models.Index(fields=['template', 'status'], name='wh_atlog_tpl_status_idx'),
        ),
        AddIndexIfMissing(
            model_name='advancedtemplatelog',
            index=models.Index(fields=['to_number', 'status'], name='wh_atlog_to_status_idx'),
        ),
        AddIndexIfMissing(
            model_name='advancedtemplatelog',
            index=models.Index(fields=['whatsapp_message_id'], name='wh_atlog_msg_id_idx'),
        ),
    ]
