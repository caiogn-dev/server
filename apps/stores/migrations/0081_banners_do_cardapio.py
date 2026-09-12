import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.stores.models.base


class Migration(migrations.Migration):
    """Carrossel de até 3 banners por loja, separado da capa (`Store.banner`)."""

    dependencies = [('stores', '0080_acrescimo_do_vale')]

    operations = [
        migrations.CreateModel(
            name='StoreBanner',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('image', models.ImageField(upload_to='stores/banners/carrossel/', validators=[apps.stores.models.base._validate_image_upload])),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='banners', to='stores.store')),
            ],
            options={'db_table': 'store_banners', 'ordering': ['position', 'created_at']},
        ),
    ]
