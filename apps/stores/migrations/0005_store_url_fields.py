from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0004_encrypt_payment_credentials'),
    ]

    operations = [
        migrations.AddField(
            model_name='store',
            name='website_url',
            field=models.URLField(blank=True, help_text='Store website'),
        ),
        migrations.AddField(
            model_name='store',
            name='menu_url',
            field=models.URLField(blank=True, help_text='Online menu URL'),
        ),
        migrations.AddField(
            model_name='store',
            name='order_url',
            field=models.URLField(blank=True, help_text='Direct order link'),
        ),
    ]
