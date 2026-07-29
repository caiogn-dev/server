import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


class BioStatsApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='stats-owner', email='stats-owner@example.com', password='test-pass'
        )
        self.other = User.objects.create_user(
            username='stats-other', email='stats-other@example.com', password='test-pass'
        )
        self.store = Store.objects.create(
            name='Stats Store', slug='stats-store', owner=self.owner, status='active', plan='pro'
        )
        self.url = f'/api/v1/stores/stores/{self.store.id}/bio-stats/'
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_stats_payload(self):
        today = timezone.localdate()
        old = today - datetime.timedelta(days=40)
        BioClickStat.objects.create(store=self.store, date=today, link_key='page:view', clicks=7)
        BioClickStat.objects.create(store=self.store, date=today, link_key='auto:menu', clicks=3)
        link = StoreBioLink.objects.create(store=self.store, title='Pesquisa', url='https://f.gle/x')
        BioClickStat.objects.create(store=self.store, date=today, link_key=f'custom:{link.id}', clicks=5)
        BioClickStat.objects.create(store=self.store, date=old, link_key='page:view', clicks=99)
        data = self.client.get(self.url).json()
        self.assertEqual(data['page_views']['total'], 7)  # 99 fora da janela de 30d
        totals = {l['key']: l['total'] for l in data['links']}
        self.assertEqual(totals[f'custom:{link.id}'], 5)
        self.assertEqual(totals['auto:menu'], 3)
        titles = {l['key']: l['title'] for l in data['links']}
        self.assertEqual(titles[f'custom:{link.id}'], 'Pesquisa')
        self.assertEqual(titles['auto:menu'], 'Fazer pedido')
        self.assertEqual(data['links'][0]['key'], f'custom:{link.id}')  # ordenado desc

    def test_gate_403_on_free(self):
        self.store.plan = 'free'
        self.store.save(update_fields=['plan'])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Pro', resp.json()['detail'])

    def test_non_owner_404(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
