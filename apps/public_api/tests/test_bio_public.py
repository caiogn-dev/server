from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


def make_store(**kw):
    owner = kw.pop('owner')
    defaults = dict(
        status='active',
        whatsapp_number='63999990000',
        address='Rua X, 1', city='Palmas', state='TO',
        plan='free',
    )
    defaults.update(kw)
    return Store.objects.create(owner=owner, **defaults)


class PublicBioApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='pub-bio', email='pub-bio@example.com', password='test-pass'
        )
        self.store = make_store(owner=self.owner, name='Bio Pub', slug='bio-pub')
        self.client = APIClient()
        self.url = '/api/v1/public/bio-pub/bio/'

    def test_payload_has_auto_links_and_branding(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        keys = [l['key'] for l in data['links']]
        self.assertIn('auto:menu', keys)
        self.assertIn('auto:whatsapp', keys)
        self.assertIn('auto:maps', keys)
        self.assertNotIn('auto:instagram', keys)  # sem instagram_url configurada
        self.assertTrue(data['show_branding'])  # plano free
        self.assertEqual(data['store']['slug'], 'bio-pub')
        menu = next(l for l in data['links'] if l['key'] == 'auto:menu')
        self.assertIn('/bio-pub', menu['url'])
        wa = next(l for l in data['links'] if l['key'] == 'auto:whatsapp')
        self.assertIn('wa.me/5563999990000', wa['url'])

    def test_settings_toggle_hides_auto_link_and_headline(self):
        self.store.metadata = {
            'bio_settings': {
                'headline': 'Salada boa!',
                'links': {'whatsapp': False},
                'instagram_url': 'https://instagram.com/bio.pub',
            }
        }
        self.store.save(update_fields=['metadata'])
        data = self.client.get(self.url).json()
        keys = [l['key'] for l in data['links']]
        self.assertNotIn('auto:whatsapp', keys)
        self.assertIn('auto:instagram', keys)
        self.assertEqual(data['headline'], 'Salada boa!')

    def test_custom_links_only_on_pro_and_hidden_on_free(self):
        StoreBioLink.objects.create(store=self.store, title='Pesquisa', url='https://forms.gle/x', sort_order=1)
        StoreBioLink.objects.create(store=self.store, title='Inativo', url='https://x.com', is_active=False)
        data = self.client.get(self.url).json()
        self.assertNotIn('custom', ' '.join(l['key'] for l in data['links']))  # free esconde
        self.store.plan = 'pro'
        self.store.save(update_fields=['plan'])
        data = self.client.get(self.url).json()
        custom = [l for l in data['links'] if l['key'].startswith('custom:')]
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]['title'], 'Pesquisa')
        self.assertFalse(data['show_branding'])  # pro remove branding

    def test_get_increments_page_view(self):
        self.client.get(self.url)
        self.client.get(self.url)
        stat = BioClickStat.objects.get(store=self.store, date=timezone.localdate(), link_key='page:view')
        self.assertEqual(stat.clicks, 2)

    def test_unknown_or_inactive_store_404(self):
        self.assertEqual(self.client.get('/api/v1/public/nope/bio/').status_code, 404)
        self.store.status = 'inactive'
        self.store.save(update_fields=['status'])
        self.assertEqual(self.client.get(self.url).status_code, 404)
