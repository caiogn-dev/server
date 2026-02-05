# Generated manually - NOOP migration (fields already exist in DB)
# The fields use_ai_agent, default_agent, and _business_hours already exist
# This migration is kept for dependency chain only

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0009_noop'),
        ('agents', '0001_initial'),
    ]

    operations = [
        # All operations removed - fields already exist in database
        # Original operations that were attempted:
        # - AddField: _business_hours (already exists)
        # - AddField: use_ai_agent (already exists)  
        # - AddField: default_agent (already exists)
        # - AlterField: account
        # - AlterField: _company_name
    ]
