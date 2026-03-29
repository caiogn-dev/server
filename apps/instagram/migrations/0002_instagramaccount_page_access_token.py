from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instagram', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='instagramaccount',
            name='page_access_token',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Page Access Token da Página Facebook conectada. Necessário para enviar DMs via Instagram.',
            ),
        ),
        migrations.AddField(
            model_name='instagramaccount',
            name='page_token_expires_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Expiração do Page Access Token (tokens de página normalmente não expiram).',
            ),
        ),
    ]
