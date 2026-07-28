from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store


class StoreClaritySettingsApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='test-pass')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='test-pass')
        self.store = Store.objects.create(name='Clarity Store', slug='clarity-store', owner=self.owner)
        self.url = f'/api/v1/stores/stores/{self.store.id}/meta-tracking/'
        self.client = APIClient()

    def test_owner_configures_clarity(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.url, {
            'clarity_id': 'abc123xyz9',
            'clarity_enabled': True,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.clarity_id, 'abc123xyz9')
        self.assertTrue(self.store.clarity_enabled)

    def test_rejects_invalid_clarity_id(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.url, {'clarity_id': '<script>alert(1)</script>'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_enable_requires_id(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.url, {'clarity_enabled': True}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_other_user_cannot_read_tracking(self):
        self.client.force_authenticate(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_public_store_payload_exposes_clarity(self):
        from apps.public_api.serializers import PublicStoreSerializer
        self.store.clarity_id = 'abc123xyz9'
        self.store.clarity_enabled = True
        self.store.save(update_fields=['clarity_id', 'clarity_enabled'])
        data = PublicStoreSerializer(self.store).data
        self.assertEqual(data['clarity_id'], 'abc123xyz9')
        self.assertTrue(data['clarity_enabled'])
