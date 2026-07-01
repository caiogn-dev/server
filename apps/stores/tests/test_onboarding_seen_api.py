from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.stores.models import Store

User = get_user_model()


class OnboardingSeenAPITest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono', email='d@t.local', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.owner)
        self.client = APIClient()

    def test_owner_marca_seen(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post('/api/v1/stores/loja/onboarding/seen/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['wizard_seen'])
        self.store.refresh_from_db()
        self.assertTrue(self.store.onboarding_wizard_seen)

    def test_idempotente(self):
        self.client.force_authenticate(self.owner)
        self.client.post('/api/v1/stores/loja/onboarding/seen/')
        r = self.client.post('/api/v1/stores/loja/onboarding/seen/')
        self.assertEqual(r.status_code, 200)

    def test_nao_owner_403(self):
        outro = User.objects.create_user(username='o2', email='o2@t.local', password='x')
        self.client.force_authenticate(outro)
        r = self.client.post('/api/v1/stores/loja/onboarding/seen/')
        self.assertEqual(r.status_code, 403)
