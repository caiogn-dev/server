# Generated migration - Add store link to CompanyProfile
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0016_drop_ecommerce_coupon_table'),
        ('automation', '0005_rename_automation__account_7d45de_idx_scheduled_m_account_8f1cce_idx_and_more'),
    ]

    operations = [
        # Add store field to CompanyProfile
        migrations.AddField(
            model_name='companyprofile',
            name='store',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='automation_profile',
                to='stores.store'
            ),
        ),
        # Make account nullable temporarily for migration
        migrations.AlterField(
            model_name='companyprofile',
            name='account',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='company_profile',
                to='whatsapp.whatsappaccount'
            ),
        ),
        # Rename existing fields to _ prefixed versions for backward compatibility
        migrations.RenameField(
            model_name='companyprofile',
            old_name='company_name',
            new_name='_company_name',
        ),
        migrations.RenameField(
            model_name='companyprofile',
            old_name='description',
            new_name='_description',
        ),
        migrations.RenameField(
            model_name='companyprofile',
            old_name='business_type',
            new_name='_business_type',
        ),
        migrations.RenameField(
            model_name='companyprofile',
            old_name='business_hours',
            new_name='_business_hours',
        ),
        # Make renamed fields nullable since they can now be read from Store
        migrations.AlterField(
            model_name='companyprofile',
            name='_company_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='companyprofile',
            name='_description',
            field=models.TextField(blank=True),
        ),
    ]
