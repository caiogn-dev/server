from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


class PublicBioRedirectTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='red-bio', email='red-bio@example.com', password='test-pass'
        )
        self.store = Store.objects.create(
            name='Red Bio', slug='red-bio', owner=self.owner,
            status='active', whatsapp_number='63988887777', plan='pro',
        )
        self.client = APIClient()

    def r(self, key):
        return self.client.get(f'/api/v1/public/red-bio/bio/r/{key}/')

    def test_auto_whatsapp_redirects_and_counts(self):
        resp = self.r('auto:whatsapp')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], 'https://wa.me/5563988887777')
        stat = BioClickStat.objects.get(
            store=self.store, date=timezone.localdate(), link_key='auto:whatsapp'
        )
        self.assertEqual(stat.clicks, 1)

    def test_custom_link_redirects(self):
        link = StoreBioLink.objects.create(store=self.store, title='P', url='https://forms.gle/x')
        resp = self.r(f'custom:{link.id}')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], 'https://forms.gle/x')

    def test_invalid_key_falls_back_to_bio_page_without_counting(self):
        resp = self.r('custom:00000000-0000-0000-0000-000000000000')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/red-bio', resp['Location'])
        self.assertFalse(
            BioClickStat.objects.filter(store=self.store, link_key__startswith='custom:').exists()
        )

    def test_no_open_redirect_via_query(self):
        resp = self.client.get('/api/v1/public/red-bio/bio/r/auto:menu/?to=https://evil.com')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp['Location'])

    def test_unknown_store_404(self):
        self.assertEqual(self.client.get('/api/v1/public/nope/bio/r/auto:menu/').status_code, 404)
