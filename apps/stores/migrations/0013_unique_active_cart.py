from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0012_storecustomer_unified_user_fk'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='storecart',
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True, user__isnull=False),
                fields=['user', 'store'],
                name='unique_active_cart_per_user_store',
            ),
        ),
    ]
