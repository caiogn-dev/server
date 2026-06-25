"""Testes do address_list aninhado no StoreCustomerSerializer."""
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from apps.stores.models import Store, StoreCustomer
from apps.stores.models.customer import StoreCustomerAddress

User = get_user_model()


class CustomerAddressNestedTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='oa', email='oa@x.com', password='x')
        self.store = Store.objects.create(name='LA', slug='la', owner=self.owner, status='active')
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = f'/api/v1/stores/customers/?store={self.store.slug}'

    def test_create_customer_with_address(self):
        resp = self.client.post(
            f'/api/v1/stores/customers/?store={self.store.slug}',
            {
                'name': 'Maria', 'phone': '63999990000',
                'address_list': [{
                    'label': 'Casa', 'street': 'Rua A', 'number': '10',
                    'neighborhood': 'Centro', 'city': 'Palmas', 'state': 'TO',
                    'zip_code': '77000000', 'is_default': True,
                }],
            }, format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        cust = StoreCustomer.objects.get(id=resp.data['id'])
        self.assertEqual(cust.address_list.count(), 1)
        addr = cust.address_list.first()
        self.assertEqual(addr.street, 'Rua A')
        self.assertTrue(addr.is_default)
        # default_address (lido por get_default_address) reflete o novo endereço
        self.assertEqual(resp.data['default_address']['street'], 'Rua A')

    def test_update_replaces_addresses(self):
        resp = self.client.post(
            f'/api/v1/stores/customers/?store={self.store.slug}',
            {'name': 'João', 'phone': '63988880000',
             'address_list': [{'street': 'Rua Velha', 'number': '1'}]},
            format='json',
        )
        cust_id = resp.data['id']
        addr_id = StoreCustomer.objects.get(id=cust_id).address_list.first().id

        # PATCH: atualiza o existente (com id) e adiciona um novo (sem id)
        resp2 = self.client.patch(
            f'/api/v1/stores/customers/{cust_id}/',
            {'address_list': [
                {'id': str(addr_id), 'street': 'Rua Nova', 'number': '2'},
                {'street': 'Trabalho', 'number': '99'},
            ]}, format='json',
        )
        self.assertEqual(resp2.status_code, 200, resp2.content)
        cust = StoreCustomer.objects.get(id=cust_id)
        streets = set(cust.address_list.values_list('street', flat=True))
        self.assertEqual(streets, {'Rua Nova', 'Trabalho'})

    def test_update_with_empty_list_removes_all(self):
        resp = self.client.post(
            f'/api/v1/stores/customers/?store={self.store.slug}',
            {'name': 'Ana', 'phone': '63977770000',
             'address_list': [{'street': 'Rua X', 'number': '5'}]},
            format='json',
        )
        cust_id = resp.data['id']
        resp2 = self.client.patch(
            f'/api/v1/stores/customers/{cust_id}/',
            {'address_list': []}, format='json',
        )
        self.assertEqual(resp2.status_code, 200, resp2.content)
        self.assertEqual(StoreCustomer.objects.get(id=cust_id).address_list.count(), 0)
