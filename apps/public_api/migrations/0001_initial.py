import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Lead',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('phone', models.CharField(max_length=30)),
                ('email', models.EmailField(blank=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('business_type', models.CharField(blank=True, max_length=100)),
                ('message', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[('new', 'Novo'), ('contacted', 'Contatado'), ('converted', 'Convertido'), ('lost', 'Perdido')],
                    default='new',
                    max_length=20,
                )),
                ('source', models.CharField(default='cadastro', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Lead',
                'verbose_name_plural': 'Leads',
                'ordering': ['-created_at'],
            },
        ),
    ]
