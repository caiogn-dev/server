from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0004_add_specialized_products_and_wishlist'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storewishlist',
            name='customer_phone',
            field=models.CharField(blank=True, db_index=True, default='', max_length=20),
        ),
    ]
