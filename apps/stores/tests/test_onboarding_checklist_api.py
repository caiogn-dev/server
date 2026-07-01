from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.stores.models import Store

User = get_user_model()


class OnboardingChecklistAPITest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono', email='dono@t.local', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.owner)
        self.client = APIClient()

    def test_owner_recebe_checklist(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get('/api/v1/stores/loja/onboarding/checklist/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['total'], 6)
        self.assertEqual(len(body['steps']), 6)
        self.assertIn('all_done', body)

    def test_nao_owner_recebe_403(self):
        outro = User.objects.create_user(username='outro', email='outro@t.local', password='x')
        self.client.force_authenticate(outro)
        r = self.client.get('/api/v1/stores/loja/onboarding/checklist/')
        self.assertEqual(r.status_code, 403)

    def test_checklist_inclui_wizard_seen(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get('/api/v1/stores/loja/onboarding/checklist/')
        self.assertIn('wizard_seen', r.json())
        self.assertFalse(r.json()['wizard_seen'])  # default
