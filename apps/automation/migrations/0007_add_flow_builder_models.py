# Migration to add Flow Builder models
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0006_rename_intent_logs_compa_f1f692_idx_intent_logs_company_b63a8c_idx_and_more'),
    ]

    operations = [
        # Modelos de Flow Builder já existem no banco
    ]
