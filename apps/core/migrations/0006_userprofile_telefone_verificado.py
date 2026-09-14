from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_uma_conta_por_telefone'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='telefone_verificado',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
