from django.test import TestCase
from django.utils import timezone

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


class BioModelsTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='bio-owner', email='bio-owner@example.com', password='test-pass'
        )
        self.store = Store.objects.create(name='Bio Store', slug='bio-store', owner=self.owner)

    def test_create_bio_link_defaults(self):
        link = StoreBioLink.objects.create(
            store=self.store, title='Pesquisa de satisfação', url='https://forms.gle/abc'
        )
        self.assertTrue(link.is_active)
        self.assertEqual(link.sort_order, 0)
        self.assertEqual(link.icon, '')
        self.assertEqual(str(link), 'Pesquisa de satisfação (bio-store)')

    def test_bio_links_ordered_by_sort_order(self):
        b = StoreBioLink.objects.create(store=self.store, title='B', url='https://b.com', sort_order=2)
        a = StoreBioLink.objects.create(store=self.store, title='A', url='https://a.com', sort_order=1)
        self.assertEqual(list(self.store.bio_links.all()), [a, b])

    def test_bump_creates_and_increments(self):
        BioClickStat.bump(self.store, 'page:view')
        BioClickStat.bump(self.store, 'page:view')
        BioClickStat.bump(self.store, 'auto:menu')
        today = timezone.localdate()
        view_stat = BioClickStat.objects.get(store=self.store, date=today, link_key='page:view')
        menu_stat = BioClickStat.objects.get(store=self.store, date=today, link_key='auto:menu')
        self.assertEqual(view_stat.clicks, 2)
        self.assertEqual(menu_stat.clicks, 1)

    def test_click_stat_unique_per_store_date_key(self):
        today = timezone.localdate()
        BioClickStat.objects.create(store=self.store, date=today, link_key='auto:menu', clicks=1)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            BioClickStat.objects.create(store=self.store, date=today, link_key='auto:menu', clicks=1)
