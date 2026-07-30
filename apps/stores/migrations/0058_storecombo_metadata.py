from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0057_storebiolink_icon_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='storecombo',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
