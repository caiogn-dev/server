# Generated manually based on model changes
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0017_add_payment_models'),
        ('automation', '0005_rename_automation__account_7d45de_idx_scheduled_m_account_8f1cce_idx_and_more'),
    ]

    operations = [
        # Add store field
        migrations.AddField(
            model_name='companyprofile',
            name='store',
            field=models.OneToOneField(
                blank=True,
                help_text='Store associated with this profile (source of business data)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='automation_profile',
                to='stores.store',
            ),
        ),
        # Rename fields to internal names (they become properties)
        migrations.RenameField(
            model_name='companyprofile',
            old_name='company_name',
            new_name='_company_name',
        ),
        migrations.RenameField(
            model_name='companyprofile',
            old_name='business_type',
            new_name='_business_type',
        ),
        migrations.RenameField(
            model_name='companyprofile',
            old_name='description',
            new_name='_description',
        ),
    ]
