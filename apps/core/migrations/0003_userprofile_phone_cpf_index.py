from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_userprofile_address_details'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='phone',
            field=models.CharField(blank=True, db_index=True, max_length=20),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='cpf',
            field=models.CharField(blank=True, db_index=True, max_length=14),
        ),
    ]
