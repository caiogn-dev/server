# Generated migration to add store link to CompanyProfile and deprecate old fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Migration to consolidate CompanyProfile with Store.
    - Adds store field if not exists
    - Deprecates old fields in favor of Store data
    """
    
    dependencies = [
        ('stores', '0001_initial'),  # Adjust as needed
        ('automation', '0001_initial'),  # Adjust as needed
    ]

    operations = [
        # Ensure store field exists (it should already exist based on the model)
        migrations.AlterField(
            model_name='companyprofile',
            name='store',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='automation_profile',
                to='stores.store',
                help_text='Link to Store (source of truth for business data)'
            ),
        ),
        
        # Add help text to deprecated fields
        migrations.AlterField(
            model_name='companyprofile',
            name='_company_name',
            field=models.CharField(
                max_length=255, 
                db_column='company_name', 
                blank=True,
                help_text='DEPRECATED: Use store.name instead'
            ),
        ),
        
        migrations.AlterField(
            model_name='companyprofile',
            name='_business_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('restaurant', 'Restaurante'),
                    ('ecommerce', 'E-commerce'),
                    ('services', 'Serviços'),
                    ('retail', 'Varejo'),
                    ('healthcare', 'Saúde'),
                    ('education', 'Educação'),
                    ('other', 'Outro')
                ],
                default='other',
                db_column='business_type',
                help_text='DEPRECATED: Use store.store_type instead'
            ),
        ),
        
        migrations.AlterField(
            model_name='companyprofile',
            name='_description',
            field=models.TextField(
                blank=True, 
                db_column='description',
                help_text='DEPRECATED: Use store.description instead'
            ),
        ),
        
        migrations.AlterField(
            model_name='companyprofile',
            name='_business_hours',
            field=models.JSONField(
                default=dict,
                blank=True,
                db_column='business_hours',
                help_text='DEPRECATED: Use store.operating_hours instead'
            ),
        ),
    ]
