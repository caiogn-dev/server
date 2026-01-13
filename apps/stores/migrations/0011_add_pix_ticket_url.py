# Generated migration for adding pix_ticket_url field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0010_configure_pastita_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeorder',
            name='pix_ticket_url',
            field=models.URLField(blank=True, help_text='Link to Mercado Pago payment page with QR code', max_length=500),
        ),
    ]
