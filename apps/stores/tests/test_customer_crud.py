"""
Tests para criação/edição de clientes via painel (Fase 2 B2).

Verifica:
  1. POST com `name` cria auth.User e StoreCustomer correto.
  2. PATCH com `name` atualiza first_name/last_name do auth.User.
  3. Cliente criado fica vinculado à store do path, não vaza para outra store.
  4. I-1: cross-tenant create via rota flat (?store=) é bloqueado com 403.
  5. M-4: duplicate POST retorna 200/201 sem 500, só um StoreCustomer existe.
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
        # Rota flat (usada pelo pastita-dash)
        self.flat_url = '/api/v1/stores/customers/'

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

    def test_create_with_nonexistent_store_slug_returns_4xx(self):
        """I-2: POST para slug inexistente retorna 4xx (não 500)."""
        bad_url = '/api/v1/stores/stores/slug-que-nao-existe-nunca/customers/'
        resp = self.client.post(bad_url, {
            'name': 'Cliente X', 'phone': '63999994444',
        }, format='json')
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertLess(resp.status_code, 500)

    # -----------------------------------------------------------------------
    # I-1: cross-tenant create via rota flat
    # -----------------------------------------------------------------------

    def test_i1_cross_tenant_flat_route_returns_403(self):
        """I-1: dono da loja-2 NÃO pode criar cliente na loja-4 via ?store=loja-4."""
        other_owner = User.objects.create_user(
            username='owner4', email='owner4@example.com', password='x'
        )
        other_store = Store.objects.create(name='Loja 4', slug='loja-4', owner=other_owner)

        resp = self.client.post(
            f'{self.flat_url}?store={other_store.slug}',
            {'name': 'Invasor', 'phone': '63911110000'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        # Nenhum cliente foi criado na loja-4
        self.assertFalse(StoreCustomer.objects.filter(store=other_store).exists())

    def test_i1_legitimate_flat_route_succeeds(self):
        """I-1: dono da loja-2 PODE criar cliente na sua própria loja via ?store=."""
        resp = self.client.post(
            f'{self.flat_url}?store={self.store.slug}',
            {'name': 'Cliente Legítimo', 'phone': '63911119999'},
            format='json',
        )
        self.assertIn(resp.status_code, (200, 201), resp.content)
        self.assertTrue(StoreCustomer.objects.filter(store=self.store).exists())

    # -----------------------------------------------------------------------
    # M-4: duplicate POST (same phone/user) não deve 500
    # -----------------------------------------------------------------------

    def test_m4_duplicate_create_does_not_500(self):
        """M-4: segundo POST com mesmo telefone não retorna 500; apenas 1 StoreCustomer."""
        payload = {'name': 'Duplicado', 'phone': '63922220000'}
        resp1 = self.client.post(self.list_url, payload, format='json')
        self.assertIn(resp1.status_code, (200, 201), resp1.content)

        resp2 = self.client.post(self.list_url, payload, format='json')
        self.assertNotEqual(resp2.status_code, 500, resp2.content)

        # Só um StoreCustomer para esse (store, user) deve existir
        count = StoreCustomer.objects.filter(store=self.store).count()
        self.assertEqual(count, 1)
