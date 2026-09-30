from django.db import migrations, models


class Migration(migrations.Migration):
    """Para quem e quando a nota foi enviada por e-mail."""

    dependencies = [
        ('fiscal', '0004_destinatariofiscal'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiscaldocument',
            name='email_enviado_para',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='fiscaldocument',
            name='email_enviado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
