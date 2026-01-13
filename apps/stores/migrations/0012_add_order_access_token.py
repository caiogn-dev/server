# Generated migration for adding access_token field to StoreOrder
# This token is required for secure public access to order details

import secrets
from django.db import migrations, models


def generate_access_tokens(apps, schema_editor):
    """Generate access tokens for existing orders."""
    StoreOrder = apps.get_model('stores', 'StoreOrder')
    for order in StoreOrder.objects.filter(access_token=''):
        order.access_token = secrets.token_urlsafe(32)
        order.save(update_fields=['access_token'])


def reverse_access_tokens(apps, schema_editor):
    """Reverse migration - clear access tokens."""
    StoreOrder = apps.get_model('stores', 'StoreOrder')
    StoreOrder.objects.all().update(access_token='')


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0011_add_pix_ticket_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeorder',
            name='access_token',
            field=models.CharField(
                db_index=True,
                default='',
                help_text='Secure token for public order access (payment page, tracking)',
                max_length=64,
            ),
            preserve_default=False,
        ),
        # Generate tokens for existing orders
        migrations.RunPython(generate_access_tokens, reverse_access_tokens),
        # Now make it unique (after all existing orders have tokens)
        migrations.AlterField(
            model_name='storeorder',
            name='access_token',
            field=models.CharField(
                db_index=True,
                help_text='Secure token for public order access (payment page, tracking)',
                max_length=64,
                unique=True,
            ),
        ),
    ]
