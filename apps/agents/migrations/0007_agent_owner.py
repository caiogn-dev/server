"""
Adiciona campo owner ao modelo Agent para escopo multi-tenant.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0006_agent_max_context_messages_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='owner',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='owned_agents',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Proprietário',
            ),
        ),
    ]
