from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store


class StoreMetaTrackingApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='test-pass')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='test-pass')
        self.store = Store.objects.create(name='Meta Store', slug='meta-store', owner=self.owner)
        self.url = f'/api/v1/stores/stores/{self.store.id}/meta-tracking/'
        self.client = APIClient()

    def test_owner_can_configure_pixel_and_token_without_token_leak(self):
        self.client.force_authenticate(self.owner)

        response = self.client.patch(self.url, {
            'meta_pixel_id': '123456789012345',
            'meta_pixel_enabled': True,
            'meta_capi_enabled': True,
            'meta_capi_access_token': 'secret-capi-token',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('meta_capi_access_token', response.data)
        self.assertTrue(response.data['meta_capi_token_configured'])
        self.store.refresh_from_db()
        self.assertEqual(self.store.meta_pixel_id, '123456789012345')
        self.assertEqual(self.store.meta_capi_access_token, 'secret-capi-token')

    def test_rejects_non_numeric_pixel_id(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.url, {'meta_pixel_id': '<script>'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_other_user_cannot_read_tracking_configuration(self):
        self.client.force_authenticate(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
