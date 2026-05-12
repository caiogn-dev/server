import uuid
import django.db.models.deletion
from django.db import migrations, models


def migrate_json_to_relational(apps, schema_editor):
    """Migra endereços do JSONField StoreCustomer.addresses para StoreCustomerAddress."""
    StoreCustomer = apps.get_model('stores', 'StoreCustomer')
    StoreCustomerAddress = apps.get_model('stores', 'StoreCustomerAddress')

    for customer in StoreCustomer.objects.exclude(addresses=[]):
        addresses = customer.addresses or []
        if not isinstance(addresses, list):
            continue

        default_index = customer.default_address_index or 0

        for i, addr in enumerate(addresses):
            if not addr or not isinstance(addr, dict):
                continue
            street = (addr.get('street') or addr.get('address') or '').strip()
            city = (addr.get('city') or '').strip()
            if not street and not city:
                continue
            StoreCustomerAddress.objects.create(
                id=uuid.uuid4(),
                customer=customer,
                label=addr.get('label', ''),
                street=street,
                number=str(addr.get('number') or '').strip(),
                complement=str(addr.get('complement') or '').strip(),
                neighborhood=str(addr.get('neighborhood') or '').strip(),
                city=city,
                state=str(addr.get('state') or '').strip()[:2].upper() or '',
                zip_code=''.join(ch for ch in str(addr.get('zip_code') or '') if ch.isdigit()),
                reference=str(addr.get('reference') or addr.get('landmark') or '').strip(),
                formatted=str(addr.get('formatted') or '').strip(),
                is_default=(i == default_index),
            )


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0010_indexes_and_constraints'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreCustomerAddress',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('label', models.CharField(blank=True, max_length=50, help_text='Ex: Casa, Trabalho')),
                ('street', models.CharField(blank=True, max_length=255)),
                ('number', models.CharField(blank=True, max_length=20)),
                ('complement', models.CharField(blank=True, max_length=100)),
                ('neighborhood', models.CharField(blank=True, max_length=100)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=2)),
                ('zip_code', models.CharField(blank=True, max_length=10)),
                ('reference', models.CharField(blank=True, max_length=255)),
                ('formatted', models.CharField(blank=True, max_length=500)),
                ('is_default', models.BooleanField(default=False)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='address_list',
                    to='stores.storecustomer',
                )),
            ],
            options={
                'verbose_name': 'Customer Address',
                'verbose_name_plural': 'Customer Addresses',
                'db_table': 'store_customer_addresses',
                'ordering': ['-is_default', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='storecustomeraddress',
            index=models.Index(fields=['customer', 'is_default'], name='custaddr_customer_default_idx'),
        ),
        migrations.AddIndex(
            model_name='storecustomeraddress',
            index=models.Index(fields=['zip_code'], name='custaddr_zip_idx'),
        ),
        migrations.RunPython(migrate_json_to_relational, reverse_code=migrations.RunPython.noop),
    ]
