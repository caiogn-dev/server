from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.stores.models import Store, StoreCustomer, StoreCustomerAddress

User = get_user_model()


class AddressNormalizationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='addr-owner', password='x')
        self.store = Store.objects.create(
            name='Addr Test', slug='addr-test', owner=self.owner,
            status='active', store_type='food',
        )
        self.user = User.objects.create_user(username='addr-user', password='x')

    def test_customer_address_table_is_source_of_truth(self):
        customer = StoreCustomer.objects.create(
            store=self.store, user=self.user, phone='5563999999999',
        )
        StoreCustomerAddress.objects.create(
            customer=customer,
            street='Rua das Saladas',
            number='42',
            neighborhood='Plano Diretor Sul',
            city='Palmas',
            state='TO',
            zip_code='77020026',
            is_default=True,
        )
        default = StoreCustomerAddress.objects.filter(
            customer=customer, is_default=True,
        ).first()
        self.assertIsNotNone(default)
        self.assertEqual(default.street, 'Rua das Saladas')

    def test_apenas_um_endereco_default_por_customer(self):
        customer = StoreCustomer.objects.create(
            store=self.store, user=self.user, phone='5563888888888',
        )
        StoreCustomerAddress.objects.create(
            customer=customer, street='Rua A', number='1',
            city='Palmas', state='TO', zip_code='77000000', is_default=True,
        )
        StoreCustomerAddress.objects.create(
            customer=customer, street='Rua B', number='2',
            city='Palmas', state='TO', zip_code='77000001', is_default=True,
        )
        defaults = StoreCustomerAddress.objects.filter(customer=customer, is_default=True)
        self.assertEqual(defaults.count(), 1)

    def test_set_as_default_clears_others(self):
        customer = StoreCustomer.objects.create(
            store=self.store, user=self.user, phone='5563777777777',
        )
        addr1 = StoreCustomerAddress.objects.create(
            customer=customer, street='Rua A', number='1',
            city='Palmas', state='TO', zip_code='77000000', is_default=True,
        )
        addr2 = StoreCustomerAddress.objects.create(
            customer=customer, street='Rua B', number='2',
            city='Palmas', state='TO', zip_code='77000001', is_default=False,
        )
        addr2.set_as_default()
        addr1.refresh_from_db()
        addr2.refresh_from_db()
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    def test_migrate_command_dry_run(self):
        customer = StoreCustomer.objects.create(
            store=self.store, user=self.user, phone='5563666666666',
            addresses=[{'street': 'Rua C', 'number': '3', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77000002'}],
            default_address_index=0,
        )
        out = StringIO()
        call_command('migrate_addresses_json', '--dry-run', stdout=out)
        self.assertIn('DRY RUN', out.getvalue())
        self.assertEqual(StoreCustomerAddress.objects.filter(customer=customer).count(), 0)

    def test_migrate_command_creates_addresses(self):
        customer = StoreCustomer.objects.create(
            store=self.store, user=self.user, phone='5563555555555',
            addresses=[{'street': 'Rua D', 'number': '4', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77000003'}],
            default_address_index=0,
        )
        call_command('migrate_addresses_json', stdout=StringIO())
        addr = StoreCustomerAddress.objects.filter(customer=customer).first()
        self.assertIsNotNone(addr)
        self.assertEqual(addr.street, 'Rua D')
        self.assertTrue(addr.is_default)
