import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Destinatário da nota como cadastro da loja. Até aqui ele era o
    `delivery_address` do pedido, e pedido de retirada não tem um completo."""

    dependencies = [
        ('stores', '0089_storeproduct_metadata'),
        ('fiscal', '0003_fiscaldocument_ambiente'),
    ]

    operations = [
        migrations.CreateModel(
            name='DestinatarioFiscal',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('documento', models.CharField(max_length=14)),
                ('nome', models.CharField(max_length=255)),
                ('inscricao_estadual', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('telefone', models.CharField(blank=True, max_length=20)),
                ('street', models.CharField(blank=True, max_length=255)),
                ('number', models.CharField(blank=True, max_length=20)),
                ('complement', models.CharField(blank=True, max_length=120)),
                ('neighborhood', models.CharField(blank=True, max_length=120)),
                ('city', models.CharField(blank=True, max_length=120)),
                ('state', models.CharField(blank=True, max_length=2)),
                ('zip_code', models.CharField(blank=True, max_length=8)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='destinatarios_fiscais', to='stores.storecustomer')),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='destinatarios_fiscais', to='stores.store')),
            ],
            options={
                'ordering': ['nome'],
            },
        ),
        migrations.AddConstraint(
            model_name='destinatariofiscal',
            constraint=models.UniqueConstraint(fields=('store', 'documento'), name='destinatario_unico_por_loja'),
        ),
    ]
