"""
Tests para criação/edição de clientes via painel (Fase 2 B2).

Verifica:
  1. POST com `name` cria auth.User e StoreCustomer correto.
  2. PATCH com `name` atualiza first_name/last_name do auth.User.
  3. Cliente criado fica vinculado à store do path, não vaza para outra store.
"""
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreCustomer

User = get_user_model()


class CustomerCrudTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner2', email='owner2@example.com', password='x'
        )
        self.store = Store.objects.create(name='Loja 2', slug='loja-2', owner=self.owner)
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = f'/api/v1/stores/stores/{self.store.slug}/customers/'

    def test_create_customer_with_name_creates_user(self):
        resp = self.client.post(self.list_url, {
            'name': 'Maria Souza Lima',
            'phone': '63999991111',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        cust = StoreCustomer.objects.get(id=resp.data['id'])
        self.assertEqual(cust.store_id, self.store.id)
        self.assertEqual(cust.user.first_name, 'Maria')
        self.assertEqual(cust.user.last_name, 'Souza Lima')
        self.assertEqual(cust.phone, '63999991111')

    def test_update_customer_name_updates_user(self):
        resp = self.client.post(self.list_url, {
            'name': 'Joao', 'phone': '63999992222',
        }, format='json')
        cid = resp.data['id']
        detail = f'{self.list_url}{cid}/'
        resp2 = self.client.patch(detail, {'name': 'Joao Pereira'}, format='json')
        self.assertEqual(resp2.status_code, 200, resp2.content)
        cust = StoreCustomer.objects.get(id=cid)
        self.assertEqual(cust.user.first_name, 'Joao')
        self.assertEqual(cust.user.last_name, 'Pereira')

    def test_create_does_not_leak_to_other_store(self):
        other_owner = User.objects.create_user(
            username='owner3', email='owner3@example.com', password='x'
        )
        other = Store.objects.create(name='Loja 3', slug='loja-3', owner=other_owner)
        resp = self.client.post(self.list_url, {
            'name': 'Cliente A', 'phone': '63999993333',
        }, format='json')
        cust = StoreCustomer.objects.get(id=resp.data['id'])
        self.assertEqual(cust.store_id, self.store.id)
        self.assertNotEqual(cust.store_id, other.id)
