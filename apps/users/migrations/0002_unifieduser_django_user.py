import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='unifieduser',
            name='django_user',
            field=models.OneToOneField(
                blank=True,
                help_text='Usuário Django correspondente (login no dashboard/site)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='unified_profile',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Django User',
            ),
        ),
        migrations.AlterField(
            model_name='unifieduser',
            name='email',
            field=models.EmailField(blank=True, db_index=True, max_length=254, null=True, unique=True, verbose_name='Email'),
        ),
    ]
