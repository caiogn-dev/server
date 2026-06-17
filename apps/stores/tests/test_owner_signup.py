"""
Testes do onboarding self-service: POST /api/v1/public/signup/
Cria dono (User) + Loja em trial (14d).
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from apps.stores.models import Store

URL = '/api/v1/public/signup/'


class OwnerSignupTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # zera o throttle (scope 'auth') entre testes
        self.client = APIClient()

    def _payload(self, **over):
        base = {
            'name': 'João Dono',
            'password': 'senhaForte123',
            'phone': '+5563999990000',
            'store_name': 'Salada do João',
            'whatsapp': '+5563999990000',
        }
        base.update(over)
        return base

    def test_signup_creates_owner_and_trial_store(self):
        resp = self.client.post(URL, self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        # token + store devolvidos
        self.assertIn('token', data)
        self.assertTrue(data['token'])
        self.assertEqual(data['store']['name'], 'Salada do João')
        self.assertEqual(data['store']['onboarding_completed'], False)

        # User criado (email derivado do telefone)
        user = User.objects.get(email='5563999990000@cardapidex.local')
        self.assertEqual(user.first_name, 'João')
        self.assertEqual(user.last_name, 'Dono')

        # Store em trial, ativa, plano starter, dono correto
        store = Store.objects.get(slug=data['store']['slug'])
        self.assertEqual(store.owner_id, user.id)
        self.assertEqual(store.status, Store.StoreStatus.ACTIVE)
        self.assertEqual(store.plan, Store.StorePlan.STARTER)
        self.assertFalse(store.onboarding_completed)
        self.assertIsNotNone(store.trial_ends_at)
        self.assertGreater(store.trial_ends_at, timezone.now())

    def test_signup_slug_autogerado_e_unico(self):
        # duas lojas com mesmo nome → slugs diferentes
        r1 = self.client.post(URL, self._payload(phone='+5563911111111'), format='json')
        r2 = self.client.post(URL, self._payload(
            name='Maria', phone='+5563922222222', email='maria@x.com'), format='json')
        self.assertEqual(r1.status_code, 201, r1.content)
        self.assertEqual(r2.status_code, 201, r2.content)
        self.assertNotEqual(r1.json()['store']['slug'], r2.json()['store']['slug'])

    def test_signup_email_duplicado_rejeitado(self):
        p = self._payload(email='dup@x.com', phone='')
        r1 = self.client.post(URL, p, format='json')
        self.assertEqual(r1.status_code, 201, r1.content)
        r2 = self.client.post(URL, self._payload(email='dup@x.com', phone='', store_name='Outra'), format='json')
        self.assertEqual(r2.status_code, 400)
        self.assertIn('email', r2.json())

    def test_signup_sem_store_name_rejeitado(self):
        r = self.client.post(URL, self._payload(store_name=''), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('store_name', r.json())

    def test_signup_senha_fraca_rejeitada(self):
        r = self.client.post(URL, self._payload(password='123'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', r.json())
