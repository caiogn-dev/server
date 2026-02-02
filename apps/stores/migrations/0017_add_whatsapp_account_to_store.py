# Generated migration - Add whatsapp_account to Store
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('whatsapp', '0001_initial'),
        ('stores', '0016_drop_ecommerce_coupon_table'),
    ]

    operations = [
        # Add whatsapp_account field to Store
        migrations.AddField(
            model_name='store',
            name='whatsapp_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stores',
                to='whatsapp.whatsappaccount',
                help_text='Primary WhatsApp account for this store'
            ),
        ),
    ]
