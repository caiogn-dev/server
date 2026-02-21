# Migration to fix index names and add company field
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0005_intentlog_is_active'),
    ]

    operations = [
        # Renomeia índices (já aplicado no banco)
        migrations.RenameIndex(
            model_name='intentlog',
            new_name='intent_logs_company_b63a8c_idx',
            old_name='intent_logs_compa_f1f692_idx',
        ),
    ]
