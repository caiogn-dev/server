from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store, StoreBioLink

BASE = '/api/v1/stores/bio-links/'


class BioLinksApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='links-owner', email='links-owner@example.com', password='test-pass'
        )
        self.other = User.objects.create_user(
            username='links-other', email='links-other@example.com', password='test-pass'
        )
        self.store = Store.objects.create(
            name='Links Store', slug='links-store', owner=self.owner, status='active', plan='pro'
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _create(self, **extra):
        payload = {'store': 'links-store', 'title': 'Pesquisa', 'url': 'https://forms.gle/x', 'icon': '📝'}
        payload.update(extra)
        return self.client.post(BASE, payload, format='json')

    def test_create_list_update_delete(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.content)
        link_id = resp.json()['id']
        resp = self.client.get(BASE, {'store': 'links-store'})
        self.assertEqual(len(resp.json()['results'] if 'results' in resp.json() else resp.json()), 1)
        resp = self.client.patch(f'{BASE}{link_id}/', {'title': 'Pesquisa 2'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(StoreBioLink.objects.get(id=link_id).title, 'Pesquisa 2')
        resp = self.client.delete(f'{BASE}{link_id}/')
        self.assertEqual(resp.status_code, 204)

    def test_create_blocked_on_free_plan_with_403(self):
        self.store.plan = 'free'
        self.store.save(update_fields=['plan'])
        resp = self._create()
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Pro', resp.json()['detail'])

    def test_non_owner_cannot_see_or_touch(self):
        resp = self._create()
        link_id = resp.json()['id']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'{BASE}{link_id}/').status_code, 404)
        self.assertEqual(
            self.client.patch(f'{BASE}{link_id}/', {'title': 'x'}, format='json').status_code, 404
        )
        resp = self._create()  # other tentando criar na loja alheia
        self.assertIn(resp.status_code, (400, 403, 404))

    def test_reorder(self):
        a = StoreBioLink.objects.create(store=self.store, title='A', url='https://a.com', sort_order=0)
        b = StoreBioLink.objects.create(store=self.store, title='B', url='https://b.com', sort_order=1)
        resp = self.client.post(
            f'{BASE}reorder/', {'store': 'links-store', 'order': [str(b.id), str(a.id)]}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((b.sort_order, a.sort_order), (0, 1))
