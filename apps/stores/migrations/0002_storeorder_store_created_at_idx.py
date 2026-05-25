from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='storeorder',
            index=models.Index(fields=['store', '-created_at'], name='storeorder_store_created_at_idx'),
        ),
    ]
