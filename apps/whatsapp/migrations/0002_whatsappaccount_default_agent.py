# Generated manually - NOOP migration (field already exists in DB)
# The field default_agent_id already exists in whatsapp_accounts table
# This migration is kept for dependency chain only

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0001_initial'),
        ('agents', '0001_initial'),
    ]

    operations = [
        # Field already exists in database - no operation needed
        # Original operation:
        # migrations.AddField(
        #     model_name='whatsappaccount',
        #     name='default_agent',
        #     field=models.ForeignKey(...)
        # ),
    ]
