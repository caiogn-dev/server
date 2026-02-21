# Add is_active field to IntentLog
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0004_intentlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='intentlog',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
