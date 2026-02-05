# Generated manually - Add whatsapp_account FK to Store

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0021_noop'),
        ('whatsapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='store',
            name='whatsapp_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stores',
                to='whatsapp.whatsappaccount',
                help_text='Conta WhatsApp associada à loja'
            ),
        ),
    ]
