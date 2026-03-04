# Add store field to CompanyProfile
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('automation', '0007_add_flow_builder_models'),
        ('stores', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Add column directly to the correct table
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE company_profiles 
                        ADD COLUMN IF NOT EXISTS store_id UUID 
                        REFERENCES stores_store(id) 
                        ON DELETE CASCADE 
                        UNIQUE;
                    """,
                    reverse_sql="""
                        ALTER TABLE company_profiles 
                        DROP COLUMN IF EXISTS store_id;
                    """
                ),
            ],
            state_operations=[
                # Update the Django model state
                migrations.AddField(
                    model_name='companyprofile',
                    name='store',
                    field=models.OneToOneField(
                        null=True,
                        blank=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='automation_profile',
                        to='stores.store',
                        help_text='Link to Store'
                    ),
                ),
            ]
        ),
    ]
